import argparse, json, os, ssl, sys
from pathlib import Path
import uvicorn
from .database import Base, get_engine, sessions, Heartbeat
from .ingest import persist
from .migrate_legacy import migrate as migrate_snapshot

def migrate(): Base.metadata.create_all(get_engine())
def seed(path):
    data=json.loads(Path(path).read_text()); migrate_snapshot(data if isinstance(data,dict) else {"scenes":data})
def serve():
    port=int(os.getenv("API_PORT","8443")); cert=os.getenv("API_TLS_CERT"); key=os.getenv("API_TLS_KEY")
    kwargs={"host":"0.0.0.0","port":port,"log_level":"info"}
    if cert and key: kwargs.update(ssl_certfile=cert,ssl_keyfile=key)
    uvicorn.run("scenescape_api.app:app",**kwargs)
def worker():
    import paho.mqtt.client as mqtt
    host=os.getenv("MQTT_HOST","broker"); port=int(os.getenv("MQTT_PORT","1883")); client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=os.getenv("MQTT_CLIENT_ID","scenescape-native-historian"))
    auth_file=os.getenv("MQTT_AUTH_FILE")
    if auth_file and Path(auth_file).is_file():
        a=json.loads(Path(auth_file).read_text()); client.username_pw_set(a.get("user"),a.get("password"))
    ca=os.getenv("MQTT_CA_FILE")
    if ca: client.tls_set(ca_certs=ca,cert_reqs=ssl.CERT_REQUIRED)
    def on_connect(c,u,f,reason,props):
        with sessions()() as db: db.merge(Heartbeat(key="mqtt",state="connected",details={"reason":str(reason)})); db.commit()
        c.subscribe("scenescape/regulated/scene/#"); c.subscribe("scenescape/event/#")
    def on_message(c,u,msg):
        with sessions()() as db: persist(db,msg.topic,msg.payload); db.commit()
    client.on_connect=on_connect; client.on_message=on_message; client.connect(host,port,60); client.loop_forever()
def main():
    p=argparse.ArgumentParser(); p.add_argument("command",choices=["serve","worker","migrate","seed"]); p.add_argument("arg",nargs="?"); a=p.parse_args();
    if a.command=="serve":serve()
    elif a.command=="worker":worker()
    elif a.command=="migrate":migrate()
    elif a.command=="seed":
        if not a.arg: p.error("seed requires a JSON path")
        seed(a.arg)
if __name__=="__main__": main()
