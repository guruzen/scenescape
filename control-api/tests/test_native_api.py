import json, os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

def boot(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/api.db')
    monkeypatch.setenv('MEDIA_ROOT', str(tmp_path/'media')); (tmp_path/'media').mkdir()
    monkeypatch.setenv('MEDIA_FALLBACK_ROOT', str(tmp_path/'samples')); (tmp_path/'samples').mkdir()
    monkeypatch.setenv('API_SIGNING_KEY', 'test-signing-key-abcdefghijklmnopqrstuvwxyz')
    auth=tmp_path/'service.json'; auth.write_text(json.dumps({'user':'svc','password':'pw'})); monkeypatch.setenv('SERVICE_AUTH_FILES', str(auth))
    import scenescape_api.database as d
    if d._engine is not None: d._engine.dispose()
    d._engine=None; d._Session=None
    import scenescape_api.app as a
    monkeypatch.setattr(a,'notify_config_change',lambda kind,uid=None: {'ok':True})
    monkeypatch.setattr(a,'notify_camera_change',lambda camera,action,previous=None: {'ok':True})
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


def test_regulated_topic_scene_id_overrides_detector_id(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'scene-live','name':'Live'}).status_code==200
    from scenescape_api.ingest import persist
    from scenescape_api.database import Observation
    from sqlalchemy import select
    payload={'id':'camera-source-1','name':'camera-source-1','scene_rate':7.5,'objects':[{'id':'person-1','translation':[2,3,0]}]}
    with d.sessions()() as db:
        persist(db,'scenescape/regulated/scene/scene-live',json.dumps(payload).encode()); db.commit()
        row=db.scalar(select(Observation).order_by(Observation.id.desc()).limit(1))
        assert row.scene_id=='scene-live'
    live=client.get('/api/v2/scenes/scene-live/live',headers=h)
    assert live.status_code==200
    assert live.json()['objects'][0]['id']=='person-1'
    assert live.json()['scene_id']=='scene-live'


def test_old_miskeyed_observation_is_read_by_regulated_topic(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'scene-old','name':'Old'}).status_code==200
    from scenescape_api.database import Observation
    from datetime import datetime, timezone
    with d.sessions()() as db:
        db.add(Observation(scene_id='camera-wrong',topic='scenescape/regulated/scene/scene-old',observed_at=datetime.now(timezone.utc),payload={'id':'camera-wrong','objects':[{'id':'x','translation':[1,1,0]}]})); db.commit()
    r=client.get('/api/v2/scenes/scene-old/live',headers=h)
    assert r.status_code==200 and r.json()['objects'][0]['id']=='x'


def test_event_scene_id_comes_from_topic(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    from scenescape_api.ingest import persist
    with d.sessions()() as db:
        persist(db,'scenescape/event/region/scene-event/zone-a/occupancy',json.dumps({'id':'camera-1','region_name':'Zone A'}).encode()); db.commit()
    incident=client.get('/api/v2/incidents',headers=h).json()[0]
    assert incident['scene_id']=='scene-event'


def test_native_camera_snapshot_bridge_returns_jpeg(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'scene-cam','name':'Camera scene'}).status_code==200
    assert client.post('/api/v2/cameras',headers=h,json={'uid':'cam-1','name':'Cam 1','scene':'scene-cam'}).status_code==200
    import scenescape_api.app as app_module
    monkeypatch.setattr(app_module,'fetch_camera_snapshot',lambda camera_id: b'\xff\xd8fake-jpeg\xff\xd9')
    r=client.get('/api/v2/cameras/cam-1/snapshot',headers=h)
    assert r.status_code==200
    assert r.headers['content-type'].startswith('image/jpeg')
    assert r.content.startswith(b'\xff\xd8')


def test_v1_service_compatibility_for_analytics(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    auth=client.post('/api/v1/auth',data={'username':'svc','password':'pw'})
    assert auth.status_code==200
    h={'Authorization':'Token '+auth.json()['token']}

    admin=headers(client)
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'scene-v1','name':'Retail'}).status_code==200
    assert client.post('/api/v2/cameras',headers=admin,json={'uid':'cam-v1','name':'Camera 1','scene':'scene-v1','translation':[1,2,0]}).status_code==200
    assert client.post('/api/v2/regions',headers=admin,json={'uid':'region-v1','name':'Zone','scene':'scene-v1','points':[[0,0],[1,0],[1,1]]}).status_code==200
    assert client.post('/api/v2/tripwires',headers=admin,json={'uid':'trip-v1','name':'Door','scene':'scene-v1','points':[[0,0],[1,1]]}).status_code==200

    scenes=client.get('/api/v1/scenes',headers=h)
    assert scenes.status_code==200
    payload=scenes.json()
    assert payload['count']==1 and payload['results'][0]['uid']=='scene-v1'
    assert payload['results'][0]['cameras'][0]['uid']=='cam-v1'
    assert payload['results'][0]['regions'][0]['uid']=='region-v1'
    assert payload['results'][0]['tripwires'][0]['uid']=='trip-v1'

    regions=client.get('/api/v1/regions?scene=scene-v1',headers=h)
    assert regions.status_code==200 and regions.json()['results'][0]['uid']=='region-v1'


def test_v1_service_camera_update_contract(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    auth=client.post('/api/v1/auth',data={'username':'svc','password':'pw'})
    h={'Authorization':'Token '+auth.json()['token']}
    admin=headers(client)
    assert client.post('/api/v2/cameras',headers=admin,json={'uid':'cam-update','name':'Camera'}).status_code==200
    updated=client.post('/api/v1/camera/cam-update',headers=h,json={'name':'Camera','intrinsics':{'fx':100.0,'fy':100.0,'cx':960.0,'cy':540.0},'resolution':[1920,1080]})
    assert updated.status_code==200
    assert updated.json()['intrinsics']['fx']==100.0
    assert updated.json()['resolution']==[1920,1080]


def test_v1_health_not_shadowed_by_compat_routes(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    r=client.get('/api/v1/health')
    assert r.status_code==200 and r.json()['status']=='ok'


def test_media_falls_back_to_packaged_sample_root(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    (tmp_path/'samples'/'HazardZoneSceneLarge.png').write_bytes(b'png-fixture')
    r=client.get('/media/HazardZoneSceneLarge.png',headers=h)
    assert r.status_code==200
    assert r.content==b'png-fixture'


def test_resource_mutations_emit_config_invalidation(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    import scenescape_api.app as app_module
    calls=[]
    monkeypatch.setattr(app_module,'notify_config_change',lambda kind,uid=None: calls.append((kind,uid)) or {'ok':True})
    created=client.post('/api/v2/scenes',headers=h,json={'uid':'notify-scene','name':'Notify'})
    assert created.status_code==200
    updated=client.put('/api/v2/scenes/notify-scene',headers=h,json={'name':'Notify 2'})
    assert updated.status_code==200
    deleted=client.delete('/api/v2/scenes/notify-scene',headers=h)
    assert deleted.status_code==200
    assert calls==[('scene','notify-scene'),('scene','notify-scene'),('scene','notify-scene')]


def test_v1_mutations_emit_config_invalidation(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    service=client.post('/api/v1/auth',data={'username':'svc','password':'pw'})
    h={'Authorization':'Token '+service.json()['token']}
    import scenescape_api.app as app_module
    calls=[]
    monkeypatch.setattr(app_module,'notify_config_change',lambda kind,uid=None: calls.append((kind,uid)) or {'ok':True})
    created=client.post('/api/v1/camera',headers=h,json={'sensor_id':'notify-cam','name':'Notify camera'})
    assert created.status_code==201
    updated=client.post('/api/v1/camera/notify-cam',headers=h,json={'name':'Notify camera 2'})
    assert updated.status_code==200
    deleted=client.delete('/api/v1/camera/notify-cam',headers=h)
    assert deleted.status_code==200
    assert calls==[('camera','notify-cam'),('camera','notify-cam'),('camera','notify-cam')]


def test_camera_mutations_emit_kubeclient_notifications(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    import scenescape_api.app as app_module
    monkeypatch.setattr(app_module,'notify_config_change',lambda kind,uid=None: {'ok':True})
    calls=[]
    monkeypatch.setattr(app_module,'notify_camera_change',lambda camera,action,previous=None: calls.append((camera,action,previous)) or {'ok':True})
    created=client.post('/api/v2/cameras',headers=h,json={'uid':'cam-side','name':'Camera Old'})
    assert created.status_code==200
    updated=client.put('/api/v2/cameras/cam-side',headers=h,json={'name':'Camera New'})
    assert updated.status_code==200
    deleted=client.delete('/api/v2/cameras/cam-side',headers=h)
    assert deleted.status_code==200
    assert [call[1] for call in calls]==['save','save','delete']
    assert calls[0][0]['uid']=='cam-side' and calls[0][2] is None
    assert calls[1][0]['name']=='Camera New' and calls[1][2]['name']=='Camera Old'
    assert calls[2][0]['name']=='Camera New'


def test_v1_camera_mutations_emit_kubeclient_notifications(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    service=client.post('/api/v1/auth',data={'username':'svc','password':'pw'})
    h={'Authorization':'Token '+service.json()['token']}
    import scenescape_api.app as app_module
    monkeypatch.setattr(app_module,'notify_config_change',lambda kind,uid=None: {'ok':True})
    calls=[]
    monkeypatch.setattr(app_module,'notify_camera_change',lambda camera,action,previous=None: calls.append((camera,action,previous)) or {'ok':True})
    created=client.post('/api/v1/camera',headers=h,json={'sensor_id':'cam-v1-side','name':'Camera Old'})
    assert created.status_code==201
    updated=client.post('/api/v1/camera/cam-v1-side',headers=h,json={'name':'Camera New'})
    assert updated.status_code==200
    deleted=client.delete('/api/v1/camera/cam-v1-side',headers=h)
    assert deleted.status_code==200
    assert [call[1] for call in calls]==['save','save','delete']
    assert calls[1][2]['name']=='Camera Old'


def test_camera_quaternion_id_rename_and_collision(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'scene-c','name':'Camera Scene'}).status_code==200
    created=client.post('/api/v2/cameras',headers=h,json={'uid':'cam-old','name':'Camera Old','scene':'scene-c'})
    assert created.status_code==200,created.text
    assert client.post('/api/v2/cameras',headers=h,json={'uid':'cam-taken','name':'Camera Taken','scene':'scene-c'}).status_code==200
    updated=client.put(
        f"/api/v2/cameras/cam-old?revision={created.json()['revision']}",
        headers=h,
        json={
            'name':'Camera Renamed','sensor_id':'cam-new','scene':'scene-c',
            'transform_type':'quaternion','translation':[1,2,3],
            'rotation':[0,0,0,1],'scale':[1,1,1],
        },
    )
    assert updated.status_code==200,updated.text
    body=updated.json()
    assert body['uid']=='cam-new' and body['transform_type']=='euler'
    assert body['rotation']==pytest.approx([0.0,0.0,0.0])
    assert client.get('/api/v2/cameras/cam-old',headers=h).status_code==404
    assert client.get('/api/v2/cameras/cam-new',headers=h).status_code==200
    collision=client.put(
        f"/api/v2/cameras/cam-new?revision={body['revision']}",
        headers=h,json={'name':'Camera Renamed','sensor_id':'cam-taken'}
    )
    assert collision.status_code==400


def test_camera_media_calibration_and_runtime_routes(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'scene-media','name':'Media Scene'}).status_code==200
    assert client.post('/api/v2/cameras',headers=h,json={'uid':'cam-media','name':'Camera Media','scene':'scene-media'}).status_code==200
    import scenescape_api.app as app_module
    monkeypatch.setattr(app_module,'fetch_camera_calibration',lambda camera_id:{
        'id':camera_id,'image':'ZmFrZQ==','intrinsics':[[570,0,320],[0,570,240],[0,0,1]],'distortion':[0,0,0,0,0]
    })
    monkeypatch.setattr(app_module,'request_camera_frame',lambda camera_id,timestamp=None,frame_type=None:{
        'camera':camera_id,'timestamp':timestamp,'frame_type':frame_type,'image':'ZmFrZQ=='
    })
    monkeypatch.setattr(app_module,'request_camera_video',lambda camera_id:b'fake-mp4')
    monkeypatch.setattr(app_module,'update_camera_runtime',lambda camera_id,body:{'ok':True,'camera':camera_id,'update':body})

    calibration=client.get('/api/v2/cameras/cam-media/calibration-frame',headers=h)
    assert calibration.status_code==200 and calibration.json()['id']=='cam-media'
    frame=client.get('/api/v2/cameras/cam-media/frame?type=raw',headers=h)
    assert frame.status_code==200 and frame.json()['frame_type']=='raw'
    video=client.get('/api/v2/cameras/cam-media/video',headers=h)
    assert video.status_code==200 and video.content==b'fake-mp4'
    assert video.headers['content-disposition'].endswith('cam-media.mp4')
    runtime=client.post('/api/v2/cameras/cam-media/runtime-update',headers=h,json={'intrinsics':{'fx':600}})
    assert runtime.status_code==200 and runtime.json()['ok'] is True

    service=client.post('/api/v1/auth',data={'username':'svc','password':'pw'}).json()['token']
    v1={'Authorization':'Token '+service}
    legacy_frame=client.get('/api/v1/frame?camera=cam-media&type=raw',headers=v1)
    assert legacy_frame.status_code==200 and legacy_frame.json()['camera']=='cam-media'
    legacy_video=client.get('/api/v1/video?camera=cam-media',headers=v1)
    assert legacy_video.status_code==200 and legacy_video.content==b'fake-mp4'


def test_camera_frame_timestamp_contract():
    from scenescape_api.camera_io import _frame_timestamp
    assert _frame_timestamp('2026-09-19T10:11:12.123Z')=='2026-09-19T10:11:12.123Z'
    with pytest.raises(ValueError):
        _frame_timestamp('not-a-timestamp')


def test_autocalibration_proxy_routes(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    import scenescape_api.app as app_module
    monkeypatch.setattr(app_module,'proxy_calibration_status',lambda:{'status':'running','version':'1.0.0'})
    monkeypatch.setattr(app_module,'proxy_scene_registration',lambda scene_id,method:{'status':'success','sceneId':scene_id,'method':method})
    monkeypatch.setattr(app_module,'proxy_camera_calibration',lambda camera_id,method,payload=None:{
        'status':'success','cameraId':camera_id,'method':method,'payload':payload
    })
    status=client.get('/api/v2/autocalibration/status',headers=h)
    assert status.status_code==200 and status.json()['status']=='running'
    registered=client.post('/api/v2/autocalibration/scenes/scene-a/registration',headers=h,json={})
    assert registered.status_code==200 and registered.json()['method']=='POST'
    camera=client.post('/api/v2/autocalibration/cameras/cam-a/calibration',headers=h,json={'image':'abc','intrinsics':[[1,0,0],[0,1,0],[0,0,1]]})
    assert camera.status_code==200 and camera.json()['payload']['image']=='abc'


def test_camera_pipeline_preview_uses_tagged_model_config(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    config_root=Path(__file__).resolve().parents[1]/'model_configs'
    monkeypatch.setenv('MODEL_CONFIGS_FOLDER',str(config_root))
    created=client.post('/api/v2/cameras',headers=h,json={
        'uid':'cam-pipeline','name':'Pipeline Camera','command':'rtsp://camera.example/live',
        'camerachain':'retail','modelconfig':'model_config.json','cv_subsystem':'AUTO'
    })
    assert created.status_code==200,created.text
    preview=client.post('/api/v2/cameras/cam-pipeline/pipeline-preview',headers=h,json={
        'command':'rtsp://camera.example/live','camerachain':'retail','modelconfig':'model_config.json'
    })
    assert preview.status_code==200,preview.text
    pipeline=preview.json()['pipeline']
    assert 'rtspsrc location=rtsp://camera.example/live' in pipeline
    assert 'gvadetect ' in pipeline
    assert 'sscape_post_inference_data_publish name=datapublisher' in pipeline
