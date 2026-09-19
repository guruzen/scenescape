import argparse
import json
import os
import ssl
from pathlib import Path

import uvicorn

from .database import Base, Heartbeat, get_engine, sessions
from .ingest import persist
from .migrate_legacy import migrate as migrate_snapshot


def migrate():
    Base.metadata.create_all(get_engine())


def seed(path):
    data = json.loads(Path(path).read_text())
    counts = migrate_snapshot(data)
    print(json.dumps({"seeded": counts}, sort_keys=True))


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

    def on_connect(c, user_data, flags, reason, properties):
        with sessions()() as db:
            db.merge(Heartbeat(key="mqtt", state="connected", details={"reason": str(reason)}))
            db.commit()
        c.subscribe("scenescape/regulated/scene/#")
        c.subscribe("scenescape/event/#")

    def on_message(c, user_data, msg):
        with sessions()() as db:
            persist(db, msg.topic, msg.payload)
            db.commit()

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, 60)
    client.loop_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["serve", "worker", "migrate", "seed"])
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


if __name__ == "__main__":
    main()
