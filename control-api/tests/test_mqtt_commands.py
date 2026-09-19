import json
import sys
import types


def install_fake_mqtt(monkeypatch, client_cls):
    paho=types.ModuleType('paho')
    mqtt_pkg=types.ModuleType('paho.mqtt')
    client_mod=types.ModuleType('paho.mqtt.client')
    class CallbackAPIVersion:
        VERSION2=2
    client_mod.CallbackAPIVersion=CallbackAPIVersion
    client_mod.Client=client_cls
    mqtt_pkg.client=client_mod
    paho.mqtt=mqtt_pkg
    monkeypatch.setitem(sys.modules,'paho',paho)
    monkeypatch.setitem(sys.modules,'paho.mqtt',mqtt_pkg)
    monkeypatch.setitem(sys.modules,'paho.mqtt.client',client_mod)


def test_scene_change_publishes_scene_and_database_topics(tmp_path, monkeypatch):
    auth=tmp_path/'browser.auth'; auth.write_text(json.dumps({'user':'u','password':'p'}))
    monkeypatch.setenv('MQTT_AUTH_FILE',str(auth)); monkeypatch.delenv('MQTT_CA_FILE',raising=False)
    import scenescape_api.mqtt_commands as commands
    published=[]
    class Info:
        def wait_for_publish(self,timeout=None): return True
    class Client:
        def __init__(self,*a,**kw): pass
        def username_pw_set(self,*a,**kw): pass
        def connect(self,*a,**kw): return 0
        def loop_start(self): pass
        def loop_stop(self): pass
        def disconnect(self): pass
        def publish(self,topic,payload,qos=0): published.append((topic,payload,qos)); return Info()
    install_fake_mqtt(monkeypatch,Client)
    result=commands.notify_config_change('scene','scene-1')
    assert result=={'ok':True}
    assert published==[
        ('scenescape/cmd/scene/update/scene-1','update',1),
        ('scenescape/cmd/database','update',1),
    ]


def test_notification_failure_is_non_fatal(monkeypatch):
    import scenescape_api.mqtt_commands as commands
    class Client:
        def __init__(self,*a,**kw): pass
        def connect(self,*a,**kw): raise OSError('broker unavailable')
    install_fake_mqtt(monkeypatch,Client)
    result=commands.notify_config_change('camera','cam1')
    assert result['ok'] is False and 'broker unavailable' in result['error']
