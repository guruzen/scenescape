import argparse
import json
import os
import ssl
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

from sqlalchemy import delete, select, text

from .database import (
    Base,
    BluetoothAnchor,
    BluetoothAssignment,
    BluetoothAudit,
    BluetoothCalibration,
    BluetoothDeviceTelemetry,
    BluetoothMeasurement,
    BluetoothProvider,
    BluetoothRawPosition,
    BluetoothTag,
    BluetoothSurveyPoint,
    BluetoothSurveySample,
    BluetoothTrackedPosition,
    Event,
    Heartbeat,
    Incident,
    Observation,
    Resource,
    get_engine,
    sessions,
)
from .bluetooth_schema import upgrade_bt01, upgrade_bt02, upgrade_bt06, upgrade_bt07, upgrade_bt08, upgrade_bt10, upgrade_bt11
from .ingest import persist
from .bluetooth_pipeline import drain_solver_queue
from .bluetooth_retention import BluetoothRetentionPolicy, purge_bluetooth_history
from .migrate_legacy import migrate as migrate_snapshot


def _enabled(name: str, default: str = "0") -> bool:
  return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _mqtt_subscription(topic: str) -> str:
  group = os.getenv("MQTT_SHARED_SUBSCRIPTION_GROUP", "").strip().strip("/")
  return f"$share/{group}/{topic}" if group else topic


def _mqtt_client_id() -> str:
  base = os.getenv("MQTT_CLIENT_ID", "scenescape-native-historian").strip()
  suffix = os.getenv("MQTT_CLIENT_ID_SUFFIX", "").strip()
  if not suffix and os.getenv("MQTT_SHARED_SUBSCRIPTION_GROUP", "").strip():
    suffix = os.getenv("HOSTNAME", "").strip()
  return f"{base}-{suffix}"[:160] if suffix else base[:160]


def run_retention():
  policy = BluetoothRetentionPolicy.from_env()
  with sessions()() as db:
    removed = purge_bluetooth_history(db, policy=policy)
    db.commit()
  print(json.dumps({"retention": policy.to_dict(), "removed": removed}, sort_keys=True))


def worker_health(*, ready: bool) -> None:
  max_age_s = max(5.0, float(os.getenv("WORKER_HEALTH_MAX_AGE_S", "90")))
  with sessions()() as db:
    heartbeat = db.scalar(select(Heartbeat).where(Heartbeat.key == "mqtt"))
  if heartbeat is None:
    raise SystemExit("MQTT worker heartbeat is missing")
  updated_at = heartbeat.updated_at
  if updated_at.tzinfo is None:
    updated_at = updated_at.replace(tzinfo=timezone.utc)
  age_s = max(0.0, (datetime.now(timezone.utc) - updated_at).total_seconds())
  if age_s > max_age_s:
    raise SystemExit(f"MQTT worker heartbeat is stale ({age_s:.1f}s)")
  if ready and heartbeat.state != "connected":
    raise SystemExit(f"MQTT worker is not ready ({heartbeat.state})")
  if not ready and heartbeat.state not in {"connected", "connecting", "degraded"}:
    raise SystemExit(f"MQTT worker is unhealthy ({heartbeat.state})")
  print(json.dumps({
      "state": heartbeat.state,
      "age_s": round(age_s, 3),
      "ready": heartbeat.state == "connected",
  }, sort_keys=True))


def migrate():
  engine = get_engine()
  Base.metadata.create_all(engine)
  upgrade_bt01(engine)
  upgrade_bt02(engine)
  upgrade_bt06(engine)
  upgrade_bt07(engine)
  upgrade_bt08(engine)
  upgrade_bt10(engine)
  upgrade_bt11(engine)
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
    for model in (
        BluetoothAudit,
        BluetoothSurveySample,
        BluetoothSurveyPoint,
        BluetoothDeviceTelemetry,
        BluetoothTrackedPosition,
        BluetoothRawPosition,
        BluetoothMeasurement,
        BluetoothAssignment,
        BluetoothCalibration,
        BluetoothTag,
        BluetoothAnchor,
        BluetoothProvider,
        Incident,
        Event,
        Observation,
        Heartbeat,
        Resource,
    ):
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
      client_id=_mqtt_client_id(),
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
    set_heartbeat("connected", reason=str(reason), client_id=_mqtt_client_id())
    topics = [
        "scenescape/regulated/scene/#",
        "scenescape/data/sensor/#",
        "scenescape/event/#",
    ]
    if _enabled("BLUETOOTH_POSITIONING_ENABLED", "1"):
      topics.append("scenescape/data/bluetooth/range/#")
    if _enabled("BLUETOOTH_TELEMETRY_ENABLED", "1"):
      topics.append("scenescape/data/bluetooth/device/#")
    for topic in topics:
      c.subscribe(_mqtt_subscription(topic))

  def on_disconnect(c, user_data, disconnect_flags, reason, properties):
    set_heartbeat("disconnected", reason=str(reason))

  def on_message(c, user_data, msg):
    try:
      with sessions()() as db:
        persisted = persist(db, msg.topic, msg.payload)
        if (
            _enabled("BLUETOOTH_POSITIONING_ENABLED", "1")
            and str(msg.topic).startswith("scenescape/data/bluetooth/range/")
        ):
          drain_solver_queue(
              db,
              maximum=max(
                  1,
                  int(os.getenv("BLUETOOTH_SOLVER_DRAIN_PER_MESSAGE", "100")),
              ),
          )
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
  parser.add_argument(
      "command",
      choices=[
          "serve",
          "worker",
          "migrate",
          "seed",
          "reset",
          "retention",
          "worker-health",
          "worker-ready",
      ],
  )
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
  elif args.command == "retention":
    run_retention()
  elif args.command == "worker-health":
    worker_health(ready=False)
  elif args.command == "worker-ready":
    worker_health(ready=True)


if __name__ == "__main__":
  main()
