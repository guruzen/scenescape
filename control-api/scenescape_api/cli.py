import argparse
import json
import os
import ssl
from pathlib import Path

import uvicorn

from sqlalchemy import delete, text

from .database import Base, Event, Heartbeat, Incident, Observation, Resource, get_engine, sessions
from .ingest import persist
from .migrate_legacy import migrate as migrate_snapshot


def migrate():
    engine = get_engine()
    Base.metadata.create_all(engine)
    # create_all() does not retrofit constraints on an existing native database.
    # Refuse to add the uniqueness guard if an earlier build already created
    # duplicate logical resources; silently deleting either row would lose data.
    with engine.begin() as connection:
        duplicates = connection.execute(text(
            "SELECT kind, uid, COUNT(*) FROM native_resources GROUP BY kind, uid HAVING COUNT(*) > 1 LIMIT 1"
        )).first()
        if duplicates:
            raise RuntimeError(
                f"Cannot enforce native resource uniqueness: duplicate {duplicates[0]}/{duplicates[1]} rows exist"
            )
        dialect = engine.dialect.name
        if dialect == "postgresql":
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_native_resources_kind_uid ON native_resources (kind, uid)"
            ))
        elif dialect == "sqlite":
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_native_resources_kind_uid ON native_resources (kind, uid)"
            ))


def seed(path):
    data = json.loads(Path(path).read_text())
    counts = migrate_snapshot(data)
    print(json.dumps({"seeded": counts}, sort_keys=True))


def reset(path=None):
    if os.getenv("SCENESCAPE_ALLOW_RESET", "").strip().lower() not in {"1", "true", "yes"}:
        raise SystemExit("reset requires SCENESCAPE_ALLOW_RESET=1")
    Base.metadata.create_all(get_engine())
    with sessions()() as db:
        for model in (Incident, Event, Observation, Heartbeat, Resource):
            db.execute(delete(model))
        db.commit()
    if path:
        seed(path)


def serve():
    port = int(os.getenv("API_PORT", "8443"))
    cert = os.getenv("API_TLS_CERT")
    key = os.getenv("API_TLS_KEY")
    kwargs = {"host": "0.0.0.0", "port": port, "log_level": "info"}
    if cert and key:
        kwargs.update(ssl_certfile=cert, ssl_keyfile=key)
    uvicorn.run("scenescape_api.app:app", **kwargs)


def worker():
    import paho.mqtt.client as mqtt

    host = os.getenv("MQTT_HOST", "broker")
    port = int(os.getenv("MQTT_PORT", "1883"))
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=os.getenv("MQTT_CLIENT_ID", "scenescape-native-historian"),
    )
    auth_file = os.getenv("MQTT_AUTH_FILE")
    if auth_file and Path(auth_file).is_file():
        auth = json.loads(Path(auth_file).read_text())
        client.username_pw_set(auth.get("user"), auth.get("password"))
    ca = os.getenv("MQTT_CA_FILE")
    if ca:
        client.tls_set(ca_certs=ca, cert_reqs=ssl.CERT_REQUIRED)

    def set_heartbeat(state, **details):
        try:
            with sessions()() as db:
                db.merge(Heartbeat(key="mqtt", state=state, details=details))
                db.commit()
        except Exception:
            # Historian liveness must not be terminated by a transient database error.
            pass

    def on_connect(c, user_data, flags, reason, properties):
        set_heartbeat("connected", reason=str(reason))
        c.subscribe("scenescape/regulated/scene/#")
        c.subscribe("scenescape/data/sensor/#")
        c.subscribe("scenescape/event/#")

    def on_disconnect(c, user_data, disconnect_flags, reason, properties):
        set_heartbeat("disconnected", reason=str(reason))

    def on_message(c, user_data, msg):
        try:
            with sessions()() as db:
                persist(db, msg.topic, msg.payload)
                db.commit()
        except Exception as exc:
            set_heartbeat("degraded", reason="ingest_error", error=type(exc).__name__, topic=str(msg.topic)[:240])

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    while True:
        try:
            set_heartbeat("connecting", host=host, port=port)
            client.connect(host, port, 60)
            client.loop_forever(retry_first_connection=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            set_heartbeat("disconnected", reason=type(exc).__name__)
            import time
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["serve", "worker", "migrate", "seed", "reset"])
    parser.add_argument("arg", nargs="?")
    args = parser.parse_args()
    if args.command == "serve":
        serve()
    elif args.command == "worker":
        worker()
    elif args.command == "migrate":
        migrate()
    elif args.command == "seed":
        if not args.arg:
            parser.error("seed requires a JSON path")
        seed(args.arg)
    elif args.command == "reset":
        reset(args.arg)


if __name__ == "__main__":
    main()
