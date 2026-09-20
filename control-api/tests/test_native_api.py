# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

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


def test_singleton_sensor_2026_2_contract(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'sensor-scene','name':'Sensor Scene'}).status_code==200

    circle=client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'sensor-circle','name':'Circle Sensor','scene':'sensor-scene',
        'area':'circle','radius':2.5,'center':[3.81,4.59],
    })
    assert circle.status_code==200,circle.text
    value=circle.json()
    assert value['uid']=='sensor-circle'
    assert value['sensor_id']=='sensor-circle'
    assert value['area']=='circle'
    assert value['center']==pytest.approx([3.81,4.59])
    assert value['translation']==pytest.approx([3.81,4.59,0.0])
    assert value['singleton_type']=='environmental'
    assert value['visible'] is False

    polygon=client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'sensor-poly','name':'Polygon Sensor','scene':'sensor-scene',
        'area':'poly','points':[[1,1],[2,2],[3,1]],'singleton_type':'attribute',
        'color_ranges':{
            'sectors':[
                {'color':'green','color_min':0},
                {'color':'yellow','color_min':2},
                {'color':'red','color_min':5},
            ],
            'range_max':10,
        },
    })
    assert polygon.status_code==200,polygon.text
    pv=polygon.json()
    assert pv['points']==[[1.0,1.0],[2.0,2.0],[3.0,1.0]]
    assert pv['translation']==[None,None,0.0]
    assert pv['singleton_type']=='attribute'
    assert pv['color_ranges']['range_max']==10

    scene_sensor=client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'sensor-scene-wide','name':'Scene Sensor','area':'scene',
    })
    assert scene_sensor.status_code==200,scene_sensor.text
    assert scene_sensor.json().get('scene') is None

    visible=client.put(
        f"/api/v2/sensors/sensor-circle?revision={value['revision']}",
        headers=h,json={'visible':True},
    )
    assert visible.status_code==200,visible.text
    assert visible.json()['visible'] is True
    assert visible.json()['radius']==2.5
    assert visible.json()['center']==pytest.approx([3.81,4.59])

    bundle=client.get('/api/v2/scenes/sensor-scene/bundle',headers=h)
    assert bundle.status_code==200
    assert {item['uid'] for item in bundle.json()['sensors']}=={'sensor-circle','sensor-poly'}


def test_singleton_sensor_validation_matches_tag(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'sensor-valid-scene','name':'Sensor Valid Scene'}).status_code==200

    assert client.post('/api/v2/sensors',headers=h,json={
        'name':'bad-area','area':'triangle'
    }).status_code==400
    assert client.post('/api/v2/sensors',headers=h,json={
        'name':'circle-no-radius','area':'circle','center':[1,2]
    }).status_code==400
    assert client.post('/api/v2/sensors',headers=h,json={
        'name':'circle-bad-center','area':'circle','radius':1,'center':[1]
    }).status_code==400
    assert client.post('/api/v2/sensors',headers=h,json={
        'name':'poly-no-points','area':'poly'
    }).status_code==400
    assert client.post('/api/v2/sensors',headers=h,json={
        'name':'poly-bad-points','area':'poly','points':[[1]]
    }).status_code==400
    assert client.post('/api/v2/sensors',headers=h,json={
        'name':'bad-scene','scene':'missing-scene'
    }).status_code==400
    assert client.post('/api/v2/sensors',headers=h,json={
        'name':'bad-ranges','color_ranges':{}
    }).status_code==400
    assert client.post('/api/v2/sensors',headers=h,json={
        'name':'bad-colors',
        'color_ranges':{
            'sectors':[{'color':'blue','color_min':0}],
            'range_max':10,
        },
    }).status_code==400

    good=client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'unique-sensor','name':'Unique Sensor','scene':'sensor-valid-scene',
    })
    assert good.status_code==200
    duplicate_name=client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'unique-sensor-2','name':'Unique Sensor','scene':'sensor-valid-scene',
    })
    assert duplicate_name.status_code==400
    duplicate_id=client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'unique-sensor','name':'Another Sensor','scene':'sensor-valid-scene',
    })
    assert duplicate_id.status_code==400


def test_singleton_sensor_id_rename_and_readonly_translation(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'sensor-rename-scene','name':'Rename Scene'}).status_code==200
    created=client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'sensor-old','name':'Renamable Sensor','scene':'sensor-rename-scene',
        'area':'circle','radius':1.5,'center':[2,3],'translation':[99,98,97],
    })
    assert created.status_code==200,created.text
    cv=created.json()
    assert cv['translation']==[2.0,3.0,0.0]
    renamed=client.put(
        f"/api/v2/sensors/sensor-old?revision={cv['revision']}",
        headers=h,json={'sensor_id':'sensor-new','name':'Renamable Sensor'},
    )
    assert renamed.status_code==200,renamed.text
    rv=renamed.json()
    assert rv['uid']=='sensor-new' and rv['sensor_id']=='sensor-new'
    assert client.get('/api/v2/sensors/sensor-old',headers=h).status_code==404
    assert client.get('/api/v2/sensors/sensor-new',headers=h).status_code==200

    taken=client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'sensor-taken','name':'Taken Sensor'
    })
    assert taken.status_code==200
    collision=client.put(
        f"/api/v2/sensors/sensor-new?revision={rv['revision']}",
        headers=h,json={'sensor_id':'sensor-taken'},
    )
    assert collision.status_code==400


def test_v1_singleton_sensor_compatibility(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    service=client.post('/api/v1/auth',data={'username':'svc','password':'pw'})
    h={'Authorization':'Token '+service.json()['token']}
    admin=headers(client)
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'sensor-v1-scene','name':'Sensor V1 Scene'}).status_code==200

    created=client.post('/api/v1/sensor',headers=h,json={
        'sensor_id':'sensor-v1','name':'Sensor V1','scene':'sensor-v1-scene',
        'area':'circle','radius':2,'center':[4,5],
    })
    assert created.status_code==201,created.text
    body=created.json()
    assert body['uid']=='sensor-v1' and body['translation']==[4.0,5.0,0.0]

    listed=client.get('/api/v1/sensors?scene=sensor-v1-scene',headers=h)
    assert listed.status_code==200
    assert listed.json()['count']==1
    assert listed.json()['results'][0]['uid']=='sensor-v1'

    updated=client.post('/api/v1/sensor/sensor-v1',headers=h,json={
        'area':'poly','points':[[0,0],[1,0],[1,1]],
    })
    assert updated.status_code==200,updated.text
    assert updated.json()['points']==[[0.0,0.0],[1.0,0.0],[1.0,1.0]]


def test_singleton_sensor_icon_lifecycle(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    created=client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'sensor-icon','name':'Sensor Icon','area':'scene'
    })
    assert created.status_code==200
    revision=created.json()['revision']
    # Valid 1x1 PNG.
    png=__import__('base64').b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC'
    )
    uploaded=client.post(
        f'/api/v2/sensors/sensor-icon/icon?revision={revision}',headers=h,
        files={'icon':('sensor.png',png,'image/png')},
    )
    assert uploaded.status_code==200,uploaded.text
    icon=uploaded.json()['icon']
    assert icon.startswith('/media/')
    assert (tmp_path/'media'/Path(icon).name).is_file()

    removed=client.delete(
        f"/api/v2/sensors/sensor-icon/icon?revision={uploaded.json()['revision']}",headers=h
    )
    assert removed.status_code==200,removed.text
    assert removed.json().get('icon') is None
    assert not (tmp_path/'media'/Path(icon).name).exists()


def test_singleton_sensor_visibility_update_skips_config_invalidation(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    import scenescape_api.app as app_module
    calls=[]
    monkeypatch.setattr(app_module,'notify_config_change',lambda kind,uid=None: calls.append((kind,uid)) or {'ok':True})
    created=client.post('/api/v2/sensors',headers=h,json={'sensor_id':'sensor-visible','name':'Visible Sensor'})
    assert created.status_code==200
    calls.clear()
    visible=client.put(
        f"/api/v2/sensors/sensor-visible?revision={created.json()['revision']}",
        headers=h,json={'visible':True},
    )
    assert visible.status_code==200 and visible.json()['visible'] is True
    assert calls==[]
    renamed=client.put(
        f"/api/v2/sensors/sensor-visible?revision={visible.json()['revision']}",
        headers=h,json={'name':'Visible Sensor 2'},
    )
    assert renamed.status_code==200
    assert calls==[('sensor','sensor-visible')]


def test_singleton_sensor_rejects_blank_explicit_id(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    r=client.post('/api/v2/sensors',headers=h,json={'sensor_id':'','name':'Blank ID Sensor'})
    assert r.status_code==400


def test_scene_delete_orphans_sensors_and_cameras(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    scene=client.post('/api/v2/scenes',headers=h,json={'uid':'delete-scene','name':'Delete Scene'})
    assert scene.status_code==200
    cam=client.post('/api/v2/cameras',headers=h,json={'uid':'delete-cam','name':'Delete Camera','scene':'delete-scene'})
    assert cam.status_code==200
    sensor=client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'delete-sensor','name':'Delete Sensor','scene':'delete-scene',
        'area':'poly','points':[[0,0],[1,0],[1,1]],
    })
    assert sensor.status_code==200
    region=client.post('/api/v2/regions',headers=h,json={
        'uid':'delete-region','name':'Delete Region','scene':'delete-scene','points':[[0,0],[1,0],[1,1]]
    })
    assert region.status_code==200
    trip=client.post('/api/v2/tripwires',headers=h,json={
        'uid':'delete-trip','name':'Delete Trip','scene':'delete-scene','points':[[0,0],[1,1]]
    })
    assert trip.status_code==200

    deleted=client.delete('/api/v2/scenes/delete-scene',headers=h)
    assert deleted.status_code==200
    orphan_sensor=client.get('/api/v2/sensors/delete-sensor',headers=h)
    orphan_camera=client.get('/api/v2/cameras/delete-cam',headers=h)
    assert orphan_sensor.status_code==200 and orphan_sensor.json().get('scene') is None
    assert orphan_camera.status_code==200 and orphan_camera.json().get('scene') is None
    assert client.get('/api/v2/regions/delete-region',headers=h).status_code==404
    assert client.get('/api/v2/tripwires/delete-trip',headers=h).status_code==404


def test_region_2026_2_contract(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'region-scene','name':'Region Scene'}).status_code==200
    minimal=client.post('/api/v2/regions',headers=h,json={
        'uid':'region-min','name':'Region Minimal','scene':'region-scene',
        'points':[[0,0],[1,0],[1,1],[0,1]],
    })
    assert minimal.status_code==200,minimal.text
    mv=minimal.json()
    assert mv['uid']=='region-min'
    assert mv['buffer_size']==0.0 and mv['height']==1.0
    assert mv['volumetric'] is False and mv['visible'] is False

    full=client.post('/api/v2/regions',headers=h,json={
        'uid':'region-full','name':'Region Full','scene':'region-scene',
        'points':[[0,0],[2,0],[2,2],[0,2]],
        'buffer_size':0.25,'height':2.5,'volumetric':True,'visible':True,
        'color_ranges':{
            'sectors':[
                {'color':'green','color_min':0},
                {'color':'yellow','color_min':2},
                {'color':'red','color_min':5},
            ],
            'range_max':10,
        },
    })
    assert full.status_code==200,full.text
    fv=full.json()
    assert fv['buffer_size']==0.25 and fv['height']==2.5
    assert fv['volumetric'] is True and fv['visible'] is True
    assert fv['color_ranges']['range_max']==10

    updated=client.put(
        f"/api/v2/regions/region-min?revision={mv['revision']}",headers=h,
        json={
            'name':'Region Minimal Updated','scene':'region-scene',
            'points':[[0,0],[3,0],[3,3],[0,3]],
            'buffer_size':0.5,'height':1.75,'volumetric':True,
            'color_ranges':{
                'sectors':[
                    {'color':'green','color_min':1},
                    {'color':'yellow','color_min':3},
                    {'color':'red','color_min':6},
                ],
                'range_max':12,
            },
        },
    )
    assert updated.status_code==200,updated.text
    uv=updated.json()
    assert uv['name']=='Region Minimal Updated'
    assert uv['points'][1]==[3.0,0.0]
    assert uv['buffer_size']==0.5 and uv['height']==1.75 and uv['volumetric'] is True
    assert uv['color_ranges']['sectors'][2]['color_min']==6


def test_region_validation_matches_tag(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'region-valid-scene','name':'Region Valid Scene'}).status_code==200
    assert client.post('/api/v2/regions',headers=h,json={
        'scene':'region-valid-scene','points':[[0,0],[1,1]]
    }).status_code==400
    assert client.post('/api/v2/regions',headers=h,json={
        'name':'No Scene','points':[[0,0],[1,1]]
    }).status_code==400
    assert client.post('/api/v2/regions',headers=h,json={
        'name':'No Points','scene':'region-valid-scene'
    }).status_code==400
    assert client.post('/api/v2/regions',headers=h,json={
        'name':'Bad Points','scene':'region-valid-scene','points':[[1]]
    }).status_code==400
    assert client.post('/api/v2/regions',headers=h,json={
        'name':'Bad Height','scene':'region-valid-scene','points':[[0,0]],'height':0
    }).status_code==400
    assert client.post('/api/v2/regions',headers=h,json={
        'name':'Bad Buffer','scene':'region-valid-scene','points':[[0,0]],'buffer_size':-1
    }).status_code==400
    assert client.post('/api/v2/regions',headers=h,json={
        'name':'Bad Color','scene':'region-valid-scene','points':[[0,0]],
        'color_ranges':{'sectors':[{'color':'blue','color_min':0}],'range_max':10},
    }).status_code==400

    good=client.post('/api/v2/regions',headers=h,json={
        'uid':'region-visible','name':'Visible','scene':'region-valid-scene','points':[[0,0],[1,0]]
    }).json()
    invalid_visible=client.put(
        f"/api/v2/regions/region-visible?revision={good['revision']}",
        headers=h,json={'visible':{'invalid':True}},
    )
    assert invalid_visible.status_code==400


def test_tripwire_2026_2_contract(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'trip-scene','name':'Trip Scene'}).status_code==200
    created=client.post('/api/v2/tripwires',headers=h,json={
        'uid':'trip-min','name':'Tripwire Minimal','scene':'trip-scene',
        'points':[[0,0],[1,0]],
    })
    assert created.status_code==200,created.text
    value=created.json()
    assert value['height']==1.0 and value['visible'] is False
    assert value['points']==[[0.0,0.0],[1.0,0.0]]

    updated=client.put(
        f"/api/v2/tripwires/trip-min?revision={value['revision']}",
        headers=h,json={'points':[[1,1],[1,0]],'height':2.25,'visible':True},
    )
    assert updated.status_code==200,updated.text
    uv=updated.json()
    assert uv['points']==[[1.0,1.0],[1.0,0.0]]
    assert uv['height']==2.25 and uv['visible'] is True

    assert client.post('/api/v2/tripwires',headers=h,json={
        'scene':'trip-scene','points':[[0,0],[1,0]]
    }).status_code==400
    assert client.post('/api/v2/tripwires',headers=h,json={
        'name':'No Scene','points':[[0,0],[1,0]]
    }).status_code==400
    assert client.post('/api/v2/tripwires',headers=h,json={
        'name':'No Points','scene':'trip-scene'
    }).status_code==400
    assert client.post('/api/v2/tripwires',headers=h,json={
        'name':'Bad Points','scene':'trip-scene','points':[[0]]
    }).status_code==400


def test_spatial_visibility_updates_skip_config_invalidation(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    import scenescape_api.app as app_module
    calls=[]
    monkeypatch.setattr(app_module,'notify_config_change',lambda kind,uid=None: calls.append((kind,uid)) or {'ok':True})
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'spatial-notify-scene','name':'Spatial Notify Scene'}).status_code==200

    region=client.post('/api/v2/regions',headers=h,json={
        'uid':'notify-region','name':'Notify Region','scene':'spatial-notify-scene','points':[[0,0],[1,0],[1,1]]
    }).json()
    trip=client.post('/api/v2/tripwires',headers=h,json={
        'uid':'notify-trip','name':'Notify Trip','scene':'spatial-notify-scene','points':[[0,0],[1,1]]
    }).json()
    calls.clear()
    assert client.put(
        f"/api/v2/regions/notify-region?revision={region['revision']}",headers=h,json={'visible':True}
    ).status_code==200
    assert client.put(
        f"/api/v2/tripwires/notify-trip?revision={trip['revision']}",headers=h,json={'visible':True}
    ).status_code==200
    assert calls==[]

    changed=client.put(
        '/api/v2/regions/notify-region?revision=2',headers=h,json={'height':2}
    )
    assert changed.status_code==200
    assert calls==[('region','notify-region')]


def test_v1_region_tripwire_compatibility(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    admin=headers(client)
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'spatial-v1-scene','name':'Spatial V1 Scene'}).status_code==200
    service=client.post('/api/v1/auth',data={'username':'svc','password':'pw'}).json()['token']
    h={'Authorization':'Token '+service}

    region=client.post('/api/v1/region',headers=h,json={
        'name':'Region V1','scene':'spatial-v1-scene','points':[[0,0],[1,0],[1,1]]
    })
    assert region.status_code==201,region.text
    rv=region.json()
    assert rv['buffer_size']==0.0 and rv['height']==1.0
    assert rv['volumetric'] is False and rv['visible'] is False

    trip=client.post('/api/v1/tripwire',headers=h,json={
        'name':'Trip V1','scene':'spatial-v1-scene','points':[[0,0],[1,1]]
    })
    assert trip.status_code==201,trip.text
    tv=trip.json()
    assert tv['height']==1.0 and tv['visible'] is False

    listed=client.get('/api/v1/regions?scene=spatial-v1-scene',headers=h)
    assert listed.status_code==200 and listed.json()['count']==1
    trips=client.get('/api/v1/tripwires?scene=spatial-v1-scene',headers=h)
    assert trips.status_code==200 and trips.json()['count']==1

    renamed=client.post(f"/api/v1/region/{rv['uid']}",headers=h,json={'name':'Region V1 Updated'})
    assert renamed.status_code==200 and renamed.json()['name']=='Region V1 Updated'


def test_sensor_telemetry_history(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    assert client.post('/api/v2/scenes',headers=h,json={'uid':'telemetry-scene','name':'Telemetry Scene'}).status_code==200
    assert client.post('/api/v2/sensors',headers=h,json={
        'sensor_id':'temperature-1','name':'Temperature','scene':'telemetry-scene','area':'scene'
    }).status_code==200
    from scenescape_api.ingest import persist, scene_id_from_topic
    assert scene_id_from_topic('scenescape/data/sensor/temperature-1')=='temperature-1'
    with d.sessions()() as db:
        persist(db,'scenescape/data/sensor/temperature-1',json.dumps({
            'timestamp':'2026-09-19T10:00:00.000Z','id':'temperature-1','value':21.5
        }).encode())
        persist(db,'scenescape/data/sensor/temperature-1',json.dumps({
            'timestamp':'2026-09-19T10:01:00.000Z','id':'temperature-1','value':22.0
        }).encode())
        db.commit()
    telemetry=client.get('/api/v2/sensors/temperature-1/telemetry?limit=10',headers=h)
    assert telemetry.status_code==200,telemetry.text
    rows=telemetry.json()
    assert [row['value'] for row in rows]==[22.0,21.5]
    assert rows[0]['sensor_id']=='temperature-1'


def test_viewer_can_read_global_object_library(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); admin=headers(client)
    asset=client.post('/api/v2/assets',headers=admin,json={'name':'person','mark_color':'#888888'})
    assert asset.status_code==200,asset.text

    import time, jwt
    viewer=jwt.encode({
        'sub':'viewer-assets','name':'Viewer Assets','roles':['scenescape-viewer'],
        'scenes':['scene-a'],'iat':int(time.time()),'exp':int(time.time())+300,
        'aud':'scenescape-api'
    },'test-signing-key-abcdefghijklmnopqrstuvwxyz',algorithm='HS256')
    h={'Authorization':'Bearer '+viewer}

    listing=client.get('/api/v2/assets',headers=h)
    assert listing.status_code==200
    assert [row['name'] for row in listing.json()]==['person']
    single=client.get(f"/api/v2/assets/{asset.json()['uid']}",headers=h)
    assert single.status_code==200 and single.json()['name']=='person'
    assert client.post('/api/v2/assets',headers=h,json={'name':'forbidden'}).status_code==403


def test_native_keycloak_user_admin_and_legacy_contract(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    import scenescape_api.app as app_module
    users={
        'alice':{
            'uid':'kc-1','username':'alice','is_active':True,'is_staff':False,'is_superuser':False,
            'first_name':'Alice','last_name':'Operator','email':'alice@example.com',
            'roles':['scenescape-viewer'],'scenes':['scene-1'],
            'acls':[{'topic':'DATA_SCENE','access':1}],
        }
    }
    monkeypatch.setattr(app_module,'keycloak_list_users',lambda:list(users.values()))
    monkeypatch.setattr(app_module,'keycloak_get_user',lambda username:users[username] if username in users else (_ for _ in ()).throw(__import__('fastapi').HTTPException(404,'User not found')))
    monkeypatch.setattr(app_module,'keycloak_create_user',lambda body:users.setdefault(body['username'],{
        'uid':'kc-2','username':body['username'],'is_active':True,'is_staff':False,'is_superuser':False,
        'first_name':'','last_name':'','email':'','roles':['scenescape-viewer'],'scenes':[],'acls':[]
    }))
    monkeypatch.setattr(app_module,'keycloak_update_user',lambda username,body:{**users[username],**body})
    monkeypatch.setattr(app_module,'keycloak_delete_user',lambda username:{'success':users.pop(username,None) is not None})

    listing=client.get('/api/v2/users',headers=h)
    assert listing.status_code==200 and listing.json()[0]['roles']==['scenescape-viewer']
    created=client.post('/api/v2/users',headers=h,json={'username':'bob','password':'pw'})
    assert created.status_code==200 and created.json()['username']=='bob'

    service=client.post('/api/v1/auth',data={'username':'svc','password':'pw'}).json()['token']
    legacy={'Authorization':'Token '+service}
    v1=client.get('/api/v1/users',headers=legacy)
    assert v1.status_code==200
    alice=next(item for item in v1.json()['results'] if item['username']=='alice')
    assert 'roles' not in alice and 'scenes' not in alice
    assert alice['acls']==[{'topic':'DATA_SCENE','access':1}]

    updated=client.post('/api/v1/user/alice',headers=legacy,json={'first_name':'Updated','is_superuser':True})
    assert updated.status_code==200
    assert updated.json()['first_name']=='Updated'
    assert updated.json()['is_superuser'] is False


def test_native_user_mutation_requires_admin(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    import time, jwt
    viewer=jwt.encode({
        'sub':'viewer','name':'Viewer','roles':['scenescape-viewer'],'scenes':['scene-a'],
        'iat':int(time.time()),'exp':int(time.time())+300,'aud':'scenescape-api'
    },'test-signing-key-abcdefghijklmnopqrstuvwxyz',algorithm='HS256')
    h={'Authorization':'Bearer '+viewer}
    import scenescape_api.app as app_module
    monkeypatch.setattr(app_module,'keycloak_list_users',lambda:[])
    assert client.get('/api/v2/users',headers=h).status_code==403
    assert client.post('/api/v2/users',headers=h,json={'username':'x','password':'y'}).status_code==403
    assert client.put('/api/v2/users/x',headers=h,json={'first_name':'x'}).status_code==403
    assert client.delete('/api/v2/users/x',headers=h).status_code==403
    assert client.get('/api/v2/security/topics',headers=h).status_code==403


def test_aclcheck_compatibility_contract(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    import scenescape_api.app as app_module
    monkeypatch.setattr(app_module,'acl_check',lambda username,topic,access:(True,4) if username=='reader' else (False,None))
    allowed=client.post('/api/v1/aclcheck',data={'username':'reader','topic':'scenescape/data/scene/s1/person','acc':'1'})
    assert allowed.status_code==200 and allowed.json()=={'result':'allow','acc':4}
    denied=client.post('/api/v1/aclcheck',json={'username':'nobody','topic':'scenescape/data/scene/s1/person','acc':1})
    assert denied.status_code==403 and denied.json()=={'result':'deny'}
    assert client.post('/api/v1/aclcheck',json={'topic':'x','acc':1}).status_code==400
    assert client.post('/api/v1/aclcheck',json={'username':'x','topic':'x','acc':'bad'}).status_code==400


def test_service_and_browser_token_schemes_remain_separate(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    service_token=client.post('/api/v1/auth',data={'username':'svc','password':'pw'}).json()['token']
    assert client.get('/api/v1/scenes',headers={'Authorization':'Token '+service_token}).status_code==200
    assert client.get('/api/v1/scenes',headers={'Authorization':'Bearer '+service_token}).status_code==401


def test_native_model_library_lifecycle_and_config_discovery(tmp_path, monkeypatch):
    models = tmp_path / 'models'
    configs = models / 'models' / 'model_configs'
    configs.mkdir(parents=True)
    (configs / 'custom.json').write_text(json.dumps({'custom': {'params': {'model': 'custom/model.xml'}}}))
    monkeypatch.setenv('MODEL_ROOT', str(models))
    monkeypatch.setenv('MODEL_CONFIGS_FOLDER', str(configs))
    client, _ = boot(tmp_path, monkeypatch)
    h = headers(client)

    listed = client.get('/api/v2/models', headers=h)
    assert listed.status_code == 200
    assert listed.json()['entries'][0]['name'] == 'models'

    discovered = client.get('/api/v2/models/configs', headers=h)
    assert discovered.status_code == 200
    assert 'custom.json' in discovered.json()['configs']

    created = client.post('/api/v2/models/directories', headers=h, json={'path': '', 'name': 'operator-model'})
    assert created.status_code == 200

    uploaded = client.post(
        '/api/v2/models/files',
        headers=h,
        data=[('path', ''), ('relative_paths', 'operator-model/weights.bin')],
        files=[('files', ('weights.bin', b'weights', 'application/octet-stream'))],
    )
    assert uploaded.status_code == 200, uploaded.text
    assert (models / 'operator-model' / 'weights.bin').read_bytes() == b'weights'

    downloaded = client.get('/api/v2/models/download?path=operator-model%2Fweights.bin', headers=h)
    assert downloaded.status_code == 200
    assert downloaded.content == b'weights'

    deleted = client.delete('/api/v2/models?path=operator-model', headers=h)
    assert deleted.status_code == 200
    assert not (models / 'operator-model').exists()


def test_native_model_zip_extraction_rejects_traversal(tmp_path, monkeypatch):
    import io
    import zipfile

    models = tmp_path / 'models'
    models.mkdir()
    monkeypatch.setenv('MODEL_ROOT', str(models))
    monkeypatch.setenv('MODEL_CONFIGS_FOLDER', str(models / 'models' / 'model_configs'))
    client, _ = boot(tmp_path, monkeypatch)
    h = headers(client)

    safe = io.BytesIO()
    with zipfile.ZipFile(safe, 'w') as archive:
        archive.writestr('nested/model.bin', b'model')
    response = client.post(
        '/api/v2/models/extract',
        headers=h,
        data={'path': ''},
        files={'file': ('bundle.zip', safe.getvalue(), 'application/zip')},
    )
    assert response.status_code == 200, response.text
    assert (models / 'bundle' / 'nested' / 'model.bin').read_bytes() == b'model'

    malicious = io.BytesIO()
    with zipfile.ZipFile(malicious, 'w') as archive:
        archive.writestr('../escape.bin', b'escape')
    response = client.post(
        '/api/v2/models/extract',
        headers=h,
        data={'path': ''},
        files={'file': ('bad.zip', malicious.getvalue(), 'application/zip')},
    )
    assert response.status_code == 400
    assert not (tmp_path / 'escape.bin').exists()


def test_nested_model_config_paths_are_supported_and_bounded(tmp_path, monkeypatch):
    root = tmp_path / 'configs'
    nested = root / 'tenant'
    nested.mkdir(parents=True)
    (nested / 'camera.json').write_text(json.dumps({'person': {'params': {'model': 'person.xml'}}}))
    monkeypatch.setenv('MODEL_CONFIGS_FOLDER', str(root))
    monkeypatch.setenv('MODEL_CONFIGS_FALLBACK_FOLDER', str(root))

    from scenescape_api.pipeline_generation import (
        PipelineGenerationValueError,
        list_model_configs,
        load_model_config,
    )

    assert list_model_configs() == ['tenant/camera.json']
    assert 'person' in load_model_config('tenant/camera.json')
    with pytest.raises(PipelineGenerationValueError):
        load_model_config('../outside.json')


def test_native_camera_telemetry_is_scoped_and_camera_id_safe(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); admin=headers(client)
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'scene-a','name':'A'}).status_code==200
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'scene-b','name':'B'}).status_code==200
    assert client.post('/api/v2/cameras',headers=admin,json={'uid':'cam_1','name':'Cam 1','scene':'scene-a'}).status_code==200
    assert client.post('/api/v2/cameras',headers=admin,json={'uid':'camX1','name':'Cam X1','scene':'scene-b'}).status_code==200

    from scenescape_api.ingest import persist
    with d.sessions()() as db:
        persist(db,'scenescape/data/camera/cam_1/person',json.dumps({
            'id':'cam_1','timestamp':'2026-01-01T00:00:00Z','objects':{'person':[{'id':1}]}
        }).encode())
        persist(db,'scenescape/data/camera/cam_1/person',json.dumps({
            'id':'cam_1','timestamp':'2026-01-01T00:00:01Z','objects':{'person':[{'id':2},{'id':3}]}
        }).encode())
        persist(db,'scenescape/data/camera/camX1/person',json.dumps({
            'id':'camX1','timestamp':'2026-01-01T00:00:01Z','objects':{'person':[{'id':9},{'id':10},{'id':11}]}
        }).encode())
        db.commit()

    value=client.get('/api/v2/cameras/cam_1/telemetry',headers=admin)
    assert value.status_code==200,value.text
    body=value.json()
    assert body['samples']==2
    assert body['fps']==1.0
    assert body['detections']==2

    import time, jwt
    viewer=jwt.encode({
        'sub':'viewer','name':'Viewer','roles':['scenescape-viewer'],'scenes':['scene-b'],
        'iat':int(time.time()),'exp':int(time.time())+300,'aud':'scenescape-api'
    },'test-signing-key-abcdefghijklmnopqrstuvwxyz',algorithm='HS256')
    scoped={'Authorization':'Bearer '+viewer}
    assert client.get('/api/v2/cameras/cam_1/telemetry',headers=scoped).status_code==403
    assert client.get('/api/v2/cameras/camX1/telemetry',headers=scoped).status_code==200


def _viewer_token(scenes):
    import time, jwt
    return jwt.encode({
        'sub':'scoped-viewer','name':'Scoped Viewer','roles':['scenescape-viewer'],'scenes':scenes,
        'iat':int(time.time()),'exp':int(time.time())+300,'aud':'scenescape-api'
    },'test-signing-key-abcdefghijklmnopqrstuvwxyz',algorithm='HS256')


def test_scoped_viewer_cannot_cross_autocalibration_boundaries(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); admin=headers(client)
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'cal-a','name':'Cal A'}).status_code==200
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'cal-b','name':'Cal B'}).status_code==200
    assert client.post('/api/v2/cameras',headers=admin,json={'uid':'cal-cam-a','name':'A','scene':'cal-a'}).status_code==200
    assert client.post('/api/v2/cameras',headers=admin,json={'uid':'cal-cam-b','name':'B','scene':'cal-b'}).status_code==200
    import scenescape_api.app as app_module
    monkeypatch.setattr(app_module,'proxy_scene_registration',lambda scene_id,method:{'scene':scene_id,'method':method})
    monkeypatch.setattr(app_module,'proxy_camera_calibration',lambda camera_id,method,body=None:{'camera':camera_id,'method':method})
    scoped={'Authorization':'Bearer '+_viewer_token(['cal-a'])}
    assert client.get('/api/v2/autocalibration/scenes/cal-a/registration',headers=scoped).status_code==200
    assert client.get('/api/v2/autocalibration/scenes/cal-b/registration',headers=scoped).status_code==403
    assert client.get('/api/v2/autocalibration/cameras/cal-cam-a/calibration',headers=scoped).status_code==200
    assert client.get('/api/v2/autocalibration/cameras/cal-cam-b/calibration',headers=scoped).status_code==403


def test_incidents_and_overview_respect_scene_scope(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); admin=headers(client)
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'scope-a','name':'Scope A'}).status_code==200
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'scope-b','name':'Scope B'}).status_code==200
    assert client.post('/api/v2/cameras',headers=admin,json={'uid':'scope-cam-a','name':'A','scene':'scope-a'}).status_code==200
    assert client.post('/api/v2/cameras',headers=admin,json={'uid':'scope-cam-b','name':'B','scene':'scope-b'}).status_code==200
    from scenescape_api.ingest import persist
    with d.sessions()() as db:
        persist(db,'scenescape/regulated/scene/scope-a',json.dumps({'id':'scope-a','objects':[]}).encode())
        persist(db,'scenescape/regulated/scene/scope-b',json.dumps({'id':'scope-b','objects':[]}).encode())
        persist(db,'scenescape/event/region/scope-a/r1/occupancy',json.dumps({'scene_id':'scope-a','region_name':'A'}).encode())
        persist(db,'scenescape/event/region/scope-b/r1/occupancy',json.dumps({'scene_id':'scope-b','region_name':'B'}).encode())
        db.commit()

    scoped={'Authorization':'Bearer '+_viewer_token(['scope-a'])}
    incidents=client.get('/api/v2/incidents',headers=scoped)
    assert incidents.status_code==200
    assert len(incidents.json())==1 and incidents.json()[0]['scene_id']=='scope-a'
    forbidden_id=client.get('/api/v2/incidents',headers=admin).json()[0]['id']
    all_incidents=client.get('/api/v2/incidents',headers=admin).json()
    forbidden_id=next(row['id'] for row in all_incidents if row['scene_id']=='scope-b')
    assert client.post(f'/api/v2/incidents/{forbidden_id}/action',headers=scoped,json={'status':'acknowledged'}).status_code==403

    overview=client.get('/api/v2/overview',headers=scoped)
    assert overview.status_code==200
    value=overview.json()
    assert value['counts']['scenes']==1
    assert value['counts']['cameras']==1
    assert value['counts']['incidents']==1
    assert value['counts']['observations']==1


def test_scene_import_zip_rejects_duplicate_basenames_symlinks_and_zip_bombs(tmp_path, monkeypatch):
    import io
    import stat
    import zipfile
    from scenescape_api.media_files import read_scene_import_zip

    duplicate=io.BytesIO()
    with zipfile.ZipFile(duplicate,'w') as archive:
        archive.writestr('scene.json',json.dumps({'name':'Scene'}))
        archive.writestr('one/map.png',b'one')
        archive.writestr('two/map.png',b'two')
    with pytest.raises(__import__('fastapi').HTTPException) as exc:
        read_scene_import_zip(duplicate.getvalue())
    assert exc.value.status_code==400
    assert 'Duplicate resource filename' in str(exc.value.detail)

    linked=io.BytesIO()
    with zipfile.ZipFile(linked,'w') as archive:
        archive.writestr('scene.json',json.dumps({'name':'Scene'}))
        info=zipfile.ZipInfo('map.glb')
        info.create_system=3
        info.external_attr=(stat.S_IFLNK | 0o777) << 16
        archive.writestr(info,'../../outside')
    with pytest.raises(__import__('fastapi').HTTPException) as exc:
        read_scene_import_zip(linked.getvalue())
    assert 'symbolic link' in str(exc.value.detail).lower()

    monkeypatch.setenv('MAX_ZIP_COMPRESSION_RATIO','2')
    bomb=io.BytesIO()
    with zipfile.ZipFile(bomb,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('scene.json',json.dumps({'name':'Scene'}))
        archive.writestr('map.bin',b'A'*(2*1024*1024))
    with pytest.raises(__import__('fastapi').HTTPException) as exc:
        read_scene_import_zip(bomb.getvalue())
    assert 'compression ratio' in str(exc.value.detail).lower()


def test_media_endpoint_denies_unreferenced_files_and_scopes_sensor_icons(tmp_path, monkeypatch):
    from PIL import Image
    import io
    client,d=boot(tmp_path,monkeypatch); admin=headers(client)
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'media-a','name':'A'}).status_code==200
    assert client.post('/api/v2/scenes',headers=admin,json={'uid':'media-b','name':'B'}).status_code==200
    assert client.post('/api/v2/sensors',headers=admin,json={'sensor_id':'sensor-b','name':'B','scene':'media-b','area':'scene'}).status_code==200
    image=io.BytesIO(); Image.new('RGB',(2,2)).save(image,format='PNG')
    uploaded=client.post('/api/v2/sensors/sensor-b/icon',headers=admin,files={'icon':('icon.png',image.getvalue(),'image/png')})
    assert uploaded.status_code==200,uploaded.text
    icon=uploaded.json()['icon']
    orphan=tmp_path/'media'/'orphan.bin'; orphan.write_bytes(b'secret')
    scoped={'Authorization':'Bearer '+_viewer_token(['media-a'])}
    assert client.get(icon,headers=scoped).status_code==403
    assert client.get('/media/orphan.bin',headers=scoped).status_code==404
    assert client.get('/media/orphan.bin',headers=admin).status_code==200


def test_native_updates_require_revision_and_reject_stale_writes(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch); h=headers(client)
    created=client.post('/api/v2/scenes',headers=h,json={'uid':'cas-scene','name':'CAS'})
    assert created.status_code==200
    assert created.json()['revision']==1
    assert client.put('/api/v2/scenes/cas-scene',headers=h,json={'name':'Missing revision'}).status_code==422
    first=client.put('/api/v2/scenes/cas-scene?revision=1',headers=h,json={'name':'First'})
    assert first.status_code==200 and first.json()['revision']==2
    stale=client.put('/api/v2/scenes/cas-scene?revision=1',headers=h,json={'name':'Stale'})
    assert stale.status_code==409
    current=client.get('/api/v2/scenes/cas-scene',headers=h).json()
    assert current['name']=='First' and current['revision']==2


def test_resource_kind_uid_unique_index_survives_migrate(tmp_path, monkeypatch):
    client,d=boot(tmp_path,monkeypatch)
    from scenescape_api.cli import migrate
    from scenescape_api.database import Resource
    from sqlalchemy.exc import IntegrityError
    migrate()
    with d.sessions()() as db:
        db.add(Resource(kind='scene',uid='duplicate-cas',payload={'uid':'duplicate-cas'},revision=1))
        db.commit()
    with d.sessions()() as db:
        db.add(Resource(kind='scene',uid='duplicate-cas',payload={'uid':'duplicate-cas'},revision=1))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
