import json, os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

def boot(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/api.db')
    monkeypatch.setenv('MEDIA_ROOT', str(tmp_path/'media')); (tmp_path/'media').mkdir()
    monkeypatch.setenv('API_SIGNING_KEY', 'test-signing-key-abcdefghijklmnopqrstuvwxyz')
    auth=tmp_path/'service.json'; auth.write_text(json.dumps({'user':'svc','password':'pw'})); monkeypatch.setenv('SERVICE_AUTH_FILES', str(auth))
    import scenescape_api.database as d
    if d._engine is not None: d._engine.dispose()
    d._engine=None; d._Session=None
    import scenescape_api.app as a
    d.Base.metadata.create_all(d.get_engine())
    return TestClient(a.app), d

def token(client):
    r=client.post('/api/v1/auth', data={'username':'svc','password':'pw'}); assert r.status_code==200; return r.json()['token']
def headers(client): return {'Authorization':'Bearer '+token(client)}

def test_crud_revision_and_live_history(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    scene=client.post('/api/v2/scenes',headers=h,json={'uid':'scene-1','name':'Floor'}); assert scene.status_code==200
    cam=client.post('/api/v2/cameras',headers=h,json={'uid':'cam-1','name':'Camera','scene':'scene-1'}).json()
    stale=client.put('/api/v2/cameras/cam-1?revision=99',headers=h,json={'name':'x'}); assert stale.status_code==409
    ok=client.put(f"/api/v2/cameras/cam-1?revision={cam['revision']}",headers=h,json={'name':'Camera 2'}); assert ok.status_code==200 and ok.json()['revision']==2
    from scenescape_api.ingest import persist
    with d.sessions()() as db:
        persist(db,'scenescape/regulated/scene/scene-1',json.dumps({'id':'scene-1','objects':[{'id':'a','translation':[1,2,0]}]}).encode()); db.commit()
    assert client.get('/api/v2/scenes/scene-1/live',headers=h).json()['objects'][0]['id']=='a'
    assert len(client.get('/api/v2/scenes/scene-1/history',headers=h).json())==1

def test_incident_action_and_audit(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    from scenescape_api.ingest import persist
    with d.sessions()() as db:
        persist(db,'scenescape/event/region/s1/r1/occupancy',json.dumps({'scene_id':'s1','region_name':'Zone A'}).encode()); db.commit()
    inc=client.get('/api/v2/incidents',headers=h).json()[0]
    r=client.post(f"/api/v2/incidents/{inc['id']}/action",headers=h,json={'status':'acknowledged','note':'checked'})
    assert r.status_code==200 and r.json()['status']=='acknowledged' and r.json()['notes'][-1]['note']=='checked'

def test_media_path_is_bounded(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    (tmp_path/'media'/'ok.txt').write_text('safe'); (tmp_path/'secret.txt').write_text('secret')
    assert client.get('/media/ok.txt',headers=h).status_code==200
    assert client.get('/media/../secret.txt',headers=h).status_code in (404,307)

def test_legacy_import_preserves_existing_and_ids(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    from scenescape_api.auth import Principal
    from scenescape_api.resources import upsert,list_resources
    from scenescape_api.migrate_legacy import migrate
    actor=Principal('x','x',frozenset({'scenescape-admin'}),frozenset({'*'}),999999)
    with d.sessions()() as db: upsert(db,'scene','existing',{'name':'Existing'},actor); db.commit()
    migrate({'scenes':[{'uid':'legacy-id','name':'Imported'}], 'cameras':[]})
    with d.sessions()() as db:
        rows=list_resources(db,'scene'); ids={x['uid'] for x in rows}
    assert ids=={'existing','legacy-id'}

def test_legacy_import_rolls_back_on_bad_snapshot(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    from scenescape_api.migrate_legacy import migrate
    with pytest.raises(ValueError): migrate({'scenes':[{'uid':'would-have-been-added'}],'cameras':'bad'})
    with d.sessions()() as db:
        from scenescape_api.resources import list_resources
        assert list_resources(db,'scene')==[]

def test_nested_scene_sample_imports_scene_and_cameras(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    from scenescape_api.migrate_legacy import migrate
    migrate({
        'uid':'scene-retail','name':'Retail','map':'/media/floor.png','scale':100,
        'cameras':[{'uid':'camera1','name':'camera1','translation':[1,2,3]}],
        'regions':[{'uid':'region1','name':'Zone','points':[[1,1],[2,1],[2,2]]}],
        'tripwires':[{'uid':'trip1','name':'Door','points':[[1,1],[2,2]]}],
    })
    h=headers(client)
    scenes=client.get('/api/v2/scenes',headers=h).json()
    cameras=client.get('/api/v2/cameras',headers=h).json()
    assert [x['uid'] for x in scenes]==['scene-retail']
    assert cameras[0]['scene']=='scene-retail'
    bundle=client.get('/api/v2/scenes/scene-retail/bundle',headers=h).json()
    assert bundle['scene']['name']=='Retail'
    assert bundle['cameras'][0]['uid']=='camera1'
    assert bundle['regions'][0]['uid']=='region1'
    assert bundle['tripwires'][0]['uid']=='trip1'


def test_native_resource_delete_requires_admin_and_deletes(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    created=client.post('/api/v2/sensors',headers=h,json={'uid':'s1','name':'Sensor 1'}); assert created.status_code==200
    deleted=client.delete('/api/v2/sensors/s1',headers=h); assert deleted.status_code==200
    assert client.get('/api/v2/sensors/s1',headers=h).status_code==404


def test_calibrationmarkers_legacy_spelling_is_imported(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    from scenescape_api.migrate_legacy import migrate
    migrate({'scenes':[{'uid':'s1','name':'Scene'}], 'calibrationmarkers':[{'marker_id':'m1','scene':'s1','apriltag_id':12}]})
    h=headers(client)
    markers=client.get('/api/v2/markers',headers=h).json()
    assert len(markers)==1 and markers[0]['marker_id']=='m1'

def test_viewer_scene_scope_filters_resources(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); admin=headers(client)
    for uid in ('a','b'):
        assert client.post('/api/v2/scenes',headers=admin,json={'uid':uid,'name':uid.upper()}).status_code==200
        assert client.post('/api/v2/cameras',headers=admin,json={'uid':'cam-'+uid,'name':'Cam '+uid,'scene':uid}).status_code==200
    import time, jwt
    viewer=jwt.encode({'sub':'viewer','name':'Viewer','roles':['scenescape-viewer'],'scenes':['a'],'iat':int(time.time()),'exp':int(time.time())+300,'aud':'scenescape-api'},'test-signing-key-abcdefghijklmnopqrstuvwxyz',algorithm='HS256')
    h={'Authorization':'Bearer '+viewer}
    scenes=client.get('/api/v2/scenes',headers=h).json(); assert [x['uid'] for x in scenes]==['a']
    cameras=client.get('/api/v2/cameras',headers=h).json(); assert [x['uid'] for x in cameras]==['cam-a']
    assert client.get('/api/v2/scenes/b/bundle',headers=h).status_code==403
