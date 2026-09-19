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


def test_scene_change_refreshes_autocalibration_registration(tmp_path, monkeypatch):
    auth=tmp_path/'browser.auth'; auth.write_text(json.dumps({'user':'u','password':'p'}))
    monkeypatch.setenv('MQTT_AUTH_FILE',str(auth)); monkeypatch.delenv('MQTT_CA_FILE',raising=False)
    monkeypatch.setenv('AUTOCALIBRATION_URL','https://autocalibration.test:8443')
    monkeypatch.delenv('UPSTREAM_CA_FILE',raising=False)
    import scenescape_api.mqtt_commands as commands
    class Info:
        def wait_for_publish(self,timeout=None): return True
    class Client:
        def __init__(self,*a,**kw): pass
        def username_pw_set(self,*a,**kw): pass
        def connect(self,*a,**kw): return 0
        def loop_start(self): pass
        def loop_stop(self): pass
        def disconnect(self): pass
        def publish(self,*a,**kw): return Info()
    install_fake_mqtt(monkeypatch,Client)
    monkeypatch.setattr(commands.ssl,'create_default_context',lambda **kw:'context')
    seen={}
    class Response:
        def __enter__(self): return self
        def __exit__(self,*a): return False
    def fake_urlopen(request,**kwargs):
        seen['url']=request.full_url; seen['method']=request.get_method(); seen.update(kwargs); return Response()
    monkeypatch.setattr(commands.urllib.request,'urlopen',fake_urlopen)
    assert commands.notify_config_change('scene','scene-1')=={'ok':True}
    assert seen['url']=='https://autocalibration.test:8443/v1/scenes/scene-1/registration'
    assert seen['method']=='PATCH' and seen['timeout']==10


def test_camera_change_publishes_2026_2_kubeclient_shape(tmp_path, monkeypatch):
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
    camera={'uid':'cam-1','name':'New Camera','resolution':[640,480],'kind':'camera','revision':2}
    previous={'uid':'cam-1','name':'Old Camera'}
    assert commands.notify_camera_change(camera,'save',previous)=={'ok':True}
    assert len(published)==1 and published[0][0]=='scenescape/cmd/kubeclient' and published[0][2]==2
    payload=json.loads(published[0][1])
    assert payload['sensor_id']=='cam-1' and payload['uid']=='cam-1'
    assert payload['previous_sensor_id']=='cam-1' and payload['previous_name']=='Old Camera'
    assert payload['action']=='save'
    assert 'kind' not in payload and 'revision' not in payload


def test_camera_change_failure_is_non_fatal(monkeypatch):
    import scenescape_api.mqtt_commands as commands
    class Client:
        def __init__(self,*a,**kw): pass
        def connect(self,*a,**kw): raise OSError('broker unavailable')
    install_fake_mqtt(monkeypatch,Client)
    result=commands.notify_camera_change({'uid':'cam1','name':'Cam'},'delete')
    assert result['ok'] is False and 'broker unavailable' in result['error']
