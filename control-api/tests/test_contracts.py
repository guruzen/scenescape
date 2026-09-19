import json

import pytest
from fastapi import HTTPException


def actor():
    from scenescape_api.auth import Principal
    return Principal('tester','Tester',frozenset({'scenescape-admin'}),frozenset({'*'}),9999999999)


def make_db(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/contracts.db')
    import scenescape_api.database as d
    if d._engine is not None:
        d._engine.dispose()
    d._engine=None; d._Session=None
    d.Base.metadata.create_all(d.get_engine())
    return d


def put_scene(db, uid='scene-1', name='Scene 1', **extra):
    from scenescape_api.resources import upsert
    with db.sessions()() as session:
        row=upsert(session,'scene',uid,{'name':name, **extra},actor()); session.commit()
        return row.uid


def test_scene_create_applies_2026_2_defaults(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        body,uid=normalize_resource(db,'scene',{'name':'Floor'},creating=True,legacy=True)
    assert uid is None
    assert body['map_type']=='map_upload'
    assert body['use_tracker'] is True
    assert body['output_lla'] is False
    assert body['mesh_translation']==[0.0,0.0,0.0]
    assert body['mesh_rotation']==[0.0,0.0,0.0]
    assert body['mesh_scale']==[1.0,1.0,1.0]
    assert body['regulated_rate']==30.0
    assert body['external_update_rate']==30.0
    assert body['camera_calibration']=='Manual'
    assert body['apriltag_size']==0.162
    assert body['number_of_localizations']==50
    assert body['global_feature']=='netvlad'
    assert body['local_feature']=={'sift':{}}
    assert body['matcher']=={'NN-ratio':{}}
    assert body['minimum_number_of_matches']==20
    assert body['inlier_threshold']==0.5
    assert body['geospatial_provider']=='google'
    assert body['map_zoom']==15.0
    assert body['map_bearing']==0.0


def test_scene_required_unknown_readonly_and_mesh_validation(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        with pytest.raises(HTTPException) as exc: normalize_resource(db,'scene',{'use_tracker':True},creating=True,legacy=True)
        assert exc.value.status_code==400
        with pytest.raises(HTTPException): normalize_resource(db,'scene',{'name':'X','tracker_config':[]},creating=True,legacy=True)
        with pytest.raises(HTTPException): normalize_resource(db,'scene',{'name':'X','uid':'bad'},creating=True,legacy=True)
        for field in ('mesh_translation','mesh_rotation','mesh_scale'):
            with pytest.raises(HTTPException): normalize_resource(db,'scene',{'name':'X',field:[1,2]},creating=True,legacy=True)


def test_scene_update_empty_body_rejected_but_partial_nonempty_allowed(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); put_scene(d)
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        with pytest.raises(HTTPException): normalize_resource(db,'scene',{},uid='scene-1',creating=False,legacy=True)
        body,uid=normalize_resource(db,'scene',{'use_tracker':False},uid='scene-1',creating=False,legacy=True)
    assert uid=='scene-1' and body=={'use_tracker':False}


def test_scene_duplicate_name_rejected_on_create_and_update(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); put_scene(d,'s1','Alpha'); put_scene(d,'s2','Beta')
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        with pytest.raises(HTTPException): normalize_resource(db,'scene',{'name':'Alpha'},creating=True,legacy=True)
        with pytest.raises(HTTPException): normalize_resource(db,'scene',{'name':'Alpha'},uid='s2',creating=False,legacy=True)
        body,_=normalize_resource(db,'scene',{'name':'Beta'},uid='s2',creating=False,legacy=True)
        assert body['name']=='Beta'


def test_scene_output_lla_requires_valid_four_corners(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); put_scene(d)
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        with pytest.raises(HTTPException): normalize_resource(db,'scene',{'output_lla':True},uid='scene-1',creating=False,legacy=True)
        corners=[[13.0,80.0,5],[13.0,80.1,5],[13.1,80.1,5],[13.1,80.0,5]]
        body,_=normalize_resource(db,'scene',{'output_lla':True,'map_corners_lla':corners},uid='scene-1',creating=False,legacy=True)
        assert body['map_corners_lla'][0]==[13.0,80.0,5.0]
        with pytest.raises(HTTPException): normalize_resource(db,'scene',{'map_corners_lla':[[91,80,0]]*4},uid='scene-1',creating=False,legacy=True)


def test_scene_numeric_and_choice_validators(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        for field,value in [('scale',0),('regulated_rate',0),('external_update_rate',-1),('map_zoom',-1),('inlier_threshold',-0.1)]:
            with pytest.raises(HTTPException): normalize_resource(db,'scene',{'name':'X',field:value},creating=True,legacy=True)
        for field,value in [('map_type','bad'),('camera_calibration','bad'),('geospatial_provider','bad')]:
            with pytest.raises(HTTPException): normalize_resource(db,'scene',{'name':'X',field:value},creating=True,legacy=True)


def test_camera_create_matches_2026_2_defaults_and_uid_generation(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); put_scene(d)
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        body,uid=normalize_resource(db,'camera',{'name':'Camera One','scene':'scene-1'},creating=True,legacy=True)
    assert uid=='Camera_One'
    assert body['name']=='Camera One'
    assert body['intrinsics']=={'fx':570.0,'fy':570.0,'cx':320.0,'cy':240.0}
    assert body['resolution']==[640,480]
    assert body['transform_type']=='3d-2d point correspondence'
    assert body['translation']==[0.0,0.0,0.0]
    assert body['rotation']==[0.0,0.0,0.0]
    assert body['scale']==[1.0,1.0,1.0]
    assert body['cv_subsystem']=='AUTO'
    assert body['undistort'] is False
    assert body['modelconfig']=='model_config.json'
    assert body['use_camera_pipeline'] is False


def test_camera_numeric_name_is_string_and_uid(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        body,uid=normalize_resource(db,'camera',{'name':0},creating=True,legacy=True)
    assert body['name']=='0' and uid=='0'


def test_camera_requires_name_on_create_and_update(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); put_scene(d)
    from scenescape_api.resources import upsert
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        with pytest.raises(HTTPException): normalize_resource(db,'camera',{'scene':'scene-1'},creating=True,legacy=True)
        upsert(db,'camera','cam1',{'name':'Cam','scene':'scene-1'},actor()); db.commit()
    with d.sessions()() as db:
        with pytest.raises(HTTPException): normalize_resource(db,'camera',{'scene':'scene-1'},uid='cam1',creating=False,legacy=True)


def test_camera_scene_must_exist_and_pipeline_requires_text(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        with pytest.raises(HTTPException): normalize_resource(db,'camera',{'name':'Cam','scene':'missing'},creating=True,legacy=True)
        with pytest.raises(HTTPException): normalize_resource(db,'camera',{'name':'Cam','use_camera_pipeline':True},creating=True,legacy=True)
        body,_=normalize_resource(db,'camera',{'name':'Cam','use_camera_pipeline':True,'camera_pipeline':'videotestsrc ! fakesink'},creating=True,legacy=True)
        assert body['camera_pipeline'].startswith('videotestsrc')


def test_camera_intrinsics_distortion_resolution_and_transform_validation(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        for intr in ({'fx':1000,'fy':1000,'cx':960,'cy':540},{'hfov':70,'vfov':50},{'fov':90}):
            body,_=normalize_resource(db,'camera',{'name':'Cam'+str(len(intr)),'intrinsics':intr},creating=True,legacy=True)
            assert 'intrinsics' in body
        with pytest.raises(HTTPException): normalize_resource(db,'camera',{'name':'Bad','intrinsics':{'fx':1}},creating=True,legacy=True)
        with pytest.raises(HTTPException): normalize_resource(db,'camera',{'name':'Bad2','resolution':[640]},creating=True,legacy=True)
        with pytest.raises(HTTPException): normalize_resource(db,'camera',{'name':'Bad3','translation':[1,2]},creating=True,legacy=True)
        with pytest.raises(HTTPException): normalize_resource(db,'camera',{'name':'Bad4','transform_type':'bad'},creating=True,legacy=True)


def test_camera_explicit_sensor_id_and_native_uid_behavior(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        _,uid=normalize_resource(db,'camera',{'name':'Legacy','sensor_id':'legacy-id'},creating=True,legacy=True)
        assert uid=='legacy-id'
        body,uid=normalize_resource(db,'camera',{'uid':'native-id','name':'Native'},creating=True,legacy=False)
        assert uid=='native-id' and 'uid' not in body


def test_camera_duplicate_name_rejected_on_create(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    from scenescape_api.resources import upsert
    from scenescape_api.contracts import normalize_resource
    with d.sessions()() as db:
        upsert(db,'camera','c1',{'name':'Same'},actor()); db.commit()
    with d.sessions()() as db:
        with pytest.raises(HTTPException): normalize_resource(db,'camera',{'name':'Same'},creating=True,legacy=True)
