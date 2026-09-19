import base64
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def actor():
    from scenescape_api.auth import Principal
    return Principal('tester','Tester',frozenset({'scenescape-admin'}),frozenset({'*'}),9999999999)


def boot(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/p1d.db')
    monkeypatch.setenv('MEDIA_ROOT', str(tmp_path/'media'))
    monkeypatch.setenv('API_SIGNING_KEY','test-signing-key-abcdefghijklmnopqrstuvwxyz')
    auth=tmp_path/'service.json'; auth.write_text(json.dumps({'user':'svc','password':'pw'})); monkeypatch.setenv('SERVICE_AUTH_FILES',str(auth))
    import scenescape_api.database as d
    if d._engine is not None: d._engine.dispose()
    d._engine=None; d._Session=None
    d.Base.metadata.create_all(d.get_engine())
    import scenescape_api.app as a
    calls=[]
    monkeypatch.setattr(a,'notify_config_change',lambda kind,uid=None:calls.append((kind,uid)) or {'ok':True})
    monkeypatch.setattr(a,'notify_camera_change',lambda *args,**kwargs:{'ok':True})
    c=TestClient(a.app)
    service=c.post('/api/v1/auth',data={'username':'svc','password':'pw'}).json()['token']
    bearer=c.post('/api/v1/auth',data={'username':'svc','password':'pw'}).json()['token']
    return c,d,{'Authorization':'Token '+service},{'Authorization':'Bearer '+bearer},calls


def png_bytes():
    from PIL import Image
    out=io.BytesIO(); Image.new('RGB',(3,2),(1,2,3)).save(out,format='PNG'); return out.getvalue()


def glb_bytes():
    import trimesh
    return trimesh.creation.box(extents=[2.0, 4.0, 1.0]).export(file_type='glb')


def polycam_zip():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('demo/mesh_info.json','{}')
        z.writestr('demo/raw.glb',glb_bytes())
        z.writestr('demo/keyframes/images/1.jpg',b'x')
        z.writestr('demo/keyframes/depth/1.png',b'x')
        z.writestr('demo/keyframes/cameras/1.json','{}')
    return out.getvalue()


def test_media_validation_and_zip_safety(tmp_path,monkeypatch):
    monkeypatch.setenv('MEDIA_ROOT',str(tmp_path/'media'))
    from scenescape_api.media_files import store_bytes, media_path, validate_polycam_zip
    url=store_bytes('floor.png',png_bytes(),kind='scene-map')
    assert media_path(url).read_bytes()==png_bytes()
    glb=store_bytes('floor.glb',glb_bytes(),kind='scene-map')
    assert media_path(glb).read_bytes().startswith(b'glTF')
    bad=tmp_path/'bad.zip'
    with zipfile.ZipFile(bad,'w') as z: z.writestr('../escape','x')
    with pytest.raises(HTTPException): validate_polycam_zip(bad)
    good=tmp_path/'poly.zip'; good.write_bytes(polycam_zip()); validate_polycam_zip(good)


def test_intrinsics_tagged_contract():
    from scenescape_api.intrinsics import calculate_camera_intrinsics
    body={
      'mapPoints':[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],
      'camPoints':[[100,100],[500,100],[500,500],[100,500]],
      'intrinsics':[[1000,0,960],[0,1000,540],[0,0,1]],
      'distortion':[0,0,0,0,0], 'imageSize':[1920,1080]
    }
    value=calculate_camera_intrinsics(body)
    assert set(value)=={'euler','position','mtx','dist'}
    with pytest.raises(HTTPException): calculate_camera_intrinsics({'distortion':[0]})
    bad=dict(body); bad['camPoints']=bad['camPoints'][:3]
    with pytest.raises(HTTPException): calculate_camera_intrinsics(bad)


def test_scene_relation_calibration_reset_and_trs_notify(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    a=c.post('/api/v1/scene',headers=v1,json={'name':'Parent','output_lla':False}); assert a.status_code==201,a.text
    b=c.post('/api/v1/scene',headers=v1,json={'name':'Child','parent':a.json()['uid'],'transform':{'translation':[1,2,3],'rotation':[0,0,0],'scale':[1,1,1]}}); assert b.status_code==201,b.text
    child=c.get('/api/v1/scene/'+b.json()['uid'],headers=v1).json()
    assert child['parent']==a.json()['uid'] and child['transform']['translation']==[1.0,2.0,3.0]
    # relationship fields must not leak into the Scene Resource payload itself
    with d.sessions()() as db:
        from scenescape_api.resources import get_resource
        payload=get_resource(db,'scene',b.json()['uid']).payload
        assert 'parent' not in payload and 'transform' not in payload
        payload['map_processed']='/media/processed.glb'; db.commit()
    r=c.post('/api/v1/scene/'+b.json()['uid'],headers=v1,json={'camera_calibration':'AprilTag'}); assert r.status_code==200
    with d.sessions()() as db:
        from scenescape_api.resources import get_resource
        assert get_resource(db,'scene',b.json()['uid']).payload['map_processed'] is None
    calls.clear()
    r=c.post('/api/v1/scene/'+b.json()['uid'],headers=v1,json={'trs_matrix':[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]}); assert r.status_code==200
    assert calls==[]


def test_v1_scene_multipart_map_and_delete_cleanup(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    r=c.post('/api/v1/scene',headers=v1,data={'name':'Floor','output_lla':'false'},files={'map':('Floor.png',png_bytes(),'image/png')})
    assert r.status_code==201,r.text
    scene=r.json(); assert scene['map'].startswith('/media/')
    path=Path(tmp_path/'media'/scene['map'].split('/media/',1)[1]); assert path.is_file()
    # Bearer-protected media is reachable through native endpoint.
    media=c.get(scene['map'],headers=v2); assert media.status_code==200 and media.content==png_bytes()
    assert c.delete('/api/v1/scene/'+scene['uid'],headers=v1).status_code==200
    assert not path.exists()


def test_polycam_map_upload_extracts_raw_glb(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    r=c.post('/api/v1/scene',headers=v1,data={'name':'Poly','output_lla':'false'},files={'map':('Poly.zip',polycam_zip(),'application/zip')})
    assert r.status_code==201,r.text
    body=r.json(); assert body['camera_calibration']=='Markerless'
    assert body['polycam_data'].endswith('.zip') and body['map'].endswith('.glb')
    assert (tmp_path/'media'/Path(body['map']).name).is_file()


def test_calibration_marker_contract_and_scene_cascade(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    scene=c.post('/api/v1/scene',headers=v1,json={'name':'Markers'}).json()['uid']
    created=c.post('/api/v1/calibrationmarker',headers=v1,json={'marker_id':'m1','apriltag_id':'7','dims':[1,2,3],'scene':scene})
    assert created.status_code==201,created.text
    assert created.json()=={'marker_id':'m1','apriltag_id':'7','dims':[1,2,3],'scene':scene}
    listing=c.get('/api/v1/calibrationmarkers',headers=v1).json(); assert listing['count']==1 and listing['results'][0]['marker_id']=='m1'
    assert c.post('/api/v1/calibrationmarker',headers=v1,json={'marker_id':'m1','apriltag_id':'8','dims':[],'scene':scene}).status_code==400
    assert c.delete('/api/v1/scene/'+scene,headers=v1).status_code==200
    assert c.get('/api/v1/calibrationmarkers',headers=v1).json()['count']==0


def make_import_zip(scene_name='ImportRoot'):
    payload={
      'name':scene_name,'scale':100,'output_lla':False,
      'cameras':[{'uid':'cam-import','name':'cam-import'}],
      'regions':[{'uid':'r1','name':'Zone','points':[[0,0],[1,0],[1,1]]}],
      'tripwires':[{'uid':'t1','name':'Door','points':[[0,0],[1,1]]}],
      'sensors':[{'sensor_id':'s1','name':'Sensor','type':'generic'}],
    }
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr(scene_name+'.json',json.dumps(payload)); z.writestr(scene_name+'.png',png_bytes())
    return out.getvalue()


def test_scene_import_success_duplicate_and_invalid(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    raw=make_import_zip()
    r=c.post('/api/v1/import-scene/',headers=v1,files={'zipFile':('scene.zip',raw,'application/zip')})
    assert r.status_code==201,r.text
    assert not any(r.json().get(k) for k in ('scene','cameras','regions','tripwires','sensors'))
    scenes=c.get('/api/v1/scenes?name=ImportRoot',headers=v1).json(); assert scenes['count']==1
    scene_uid=scenes['results'][0]['uid']
    cams=c.get('/api/v1/cameras?scene='+scene_uid,headers=v1).json(); assert cams['count']==1 and cams['results'][0]['uid']=='cam-import'
    duplicate=c.post('/api/v1/import-scene/',headers=v1,files={'zipFile':('scene.zip',raw,'application/zip')})
    assert duplicate.status_code==201 and duplicate.json()['scene']
    invalid=c.post('/api/v1/import-scene/',headers=v1,files={'zipFile':('bad.zip',b'not-a-zip','application/zip')})
    assert invalid.status_code==201 and invalid.json()['scene']


def test_calculateintrinsics_endpoint_precedes_generic_route(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    body={'mapPoints':[[0,0,0],[1,0,0],[1,1,0],[0,1,0]],'camPoints':[[100,100],[500,100],[500,500],[100,500]],'intrinsics':[[1000,0,960],[0,1000,540],[0,0,1]],'distortion':[0,0,0,0,0],'imageSize':[1920,1080]}
    r=c.post('/api/v1/calculateintrinsics',headers=v1,json=body)
    assert r.status_code==200,r.text
    assert 'mtx' in r.json()


def test_scene_import_recurses_embedded_local_children(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    child={
      'uid':'exported-child-id','name':'ImportChild','scale':100,'output_lla':False,
      'link':{'uid':'exported-link-id','child_type':'local','transform_type':'euler',
              'transform1':4,'transform2':5,'transform3':0,
              'transform4':0,'transform5':0,'transform6':0,
              'transform7':1,'transform8':1,'transform9':1},
      'cameras':[],'regions':[],'tripwires':[],'sensors':[],
    }
    root={
      'name':'ImportParent','scale':100,'output_lla':False,
      'cameras':[],'regions':[],'tripwires':[],'sensors':[],
      'children':[child],
    }
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('ImportParent.json',json.dumps(root))
        z.writestr('ImportParent.png',png_bytes())
        z.writestr('ImportChild.png',png_bytes())
    r=c.post('/api/v1/import-scene/',headers=v1,files={'zipFile':('hierarchy.zip',out.getvalue(),'application/zip')})
    assert r.status_code==201,r.text
    assert not r.json()['scene']
    parents=c.get('/api/v1/scenes?name=ImportParent',headers=v1).json()['results']
    children=c.get('/api/v1/scenes?name=ImportChild',headers=v1).json()['results']
    assert len(parents)==1 and len(children)==1
    parent_uid=parents[0]['uid']; child_uid=children[0]['uid']
    imported=c.get('/api/v1/scene/'+parent_uid,headers=v1).json()
    assert len(imported['children'])==1
    nested=imported['children'][0]
    assert nested['uid']==child_uid and nested['parent']==parent_uid
    assert nested['link']['child']==child_uid
    assert nested['link']['transform']['translation']==[4.0,5.0,0.0]


def test_marker_migration_reuses_old_scene_qualified_uid(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    from scenescape_api.auth import Principal
    from scenescape_api.resources import upsert,list_resources
    from scenescape_api.migrate_legacy import migrate
    migration_actor=Principal('old','old',frozenset({'scenescape-admin'}),frozenset({'*'}),9999999999)
    with d.sessions()() as db:
        upsert(db,'scene','s1',{'name':'Scene'},migration_actor)
        upsert(db,'marker','s1:m1',{'marker_id':'m1','scene':'s1','apriltag_id':'1','dims':[1]},migration_actor)
        db.commit()
    migrate({'calibrationmarkers':[{'marker_id':'m1','scene':'s1','apriltag_id':'2','dims':[2]}]})
    with d.sessions()() as db:
        rows=list_resources(db,'marker')
    assert len(rows)==1
    assert rows[0]['uid']=='s1:m1'
    assert rows[0]['marker_id']=='m1' and rows[0]['apriltag_id']=='2' and rows[0]['dims']==[2]


def test_glb_scene_autoalign_thumbnail_and_pose_refresh(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    r=c.post('/api/v1/scene',headers=v1,data={'name':'Mesh','output_lla':'false'},files={'map':('Mesh.glb',glb_bytes(),'model/gltf-binary')})
    assert r.status_code==201,r.text
    scene=r.json()
    assert scene['mesh_rotation']==[90.0,0.0,0.0]
    assert scene['mesh_translation']==pytest.approx([1.0,0.5,2.0])
    assert scene['scale']>0 and scene['thumbnail'].endswith('.png')
    old_thumb=Path(tmp_path/'media'/Path(scene['thumbnail']).name); assert old_thumb.is_file()
    updated=c.post('/api/v1/scene/'+scene['uid'],headers=v1,json={'mesh_rotation':[0,0,0],'mesh_translation':[2,3,0]})
    assert updated.status_code==200,updated.text
    value=updated.json(); assert value['mesh_rotation']==[0.0,0.0,0.0] and value['mesh_translation']==[2.0,3.0,0.0]
    new_thumb=Path(tmp_path/'media'/Path(value['thumbnail']).name); assert new_thumb.is_file() and new_thumb!=old_thumb
    assert not old_thumb.exists()


def test_legacy_nonnull_and_trs_visibility(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    r=c.post('/api/v1/scene',headers=v1,json={'name':'GeoOff','output_lla':False})
    assert r.status_code==201
    body=r.json(); assert 'map_processed' not in body and 'cameras' not in body and 'children' not in body
    uid=body['uid']
    matrix=[[1,0,0,10],[0,1,0,20],[0,0,1,30],[0,0,0,1]]
    assert c.post('/api/v1/scene/'+uid,headers=v1,json={'trs_matrix':matrix}).status_code==200
    assert 'trs_matrix' not in c.get('/api/v1/scene/'+uid,headers=v1).json()
    corners=[[10,20,0],[10,21,0],[11,21,0],[11,20,0]]
    r=c.post('/api/v1/scene/'+uid,headers=v1,json={'output_lla':True,'map_corners_lla':corners})
    assert r.status_code==200,r.text
    assert r.json()['trs_matrix']==matrix


def test_asset_defaults_multipart_model_remove_and_cleanup(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    minimal=c.post('/api/v1/asset',headers=v1,json={'name':'Asset_Minimal'})
    assert minimal.status_code==201,minimal.text
    m=minimal.json(); assert m['uid'].isdigit()
    assert m['x_size']==1.0 and m['y_size']==1.0 and m['z_size']==1.0
    assert m['tracking_radius']==2.0 and m['shift_type']==1 and m['mark_color']=='#888888'
    assert m['geometric_center']==[0.0,0.0,0.0] and m['friction_coefficients']==[0.5,0.4]
    assert c.post('/api/v1/asset',headers=v1,json={'name':'Asset_Minimal'}).status_code==400

    upload=c.post('/api/v1/asset',headers=v1,data={'name':'3D Object'},files={'model_3d':('box.glb',glb_bytes(),'model/gltf-binary')})
    assert upload.status_code==201,upload.text
    asset=upload.json(); path=Path(tmp_path/'media'/Path(asset['model_3d']).name); assert path.is_file()
    removed=c.post('/api/v1/asset/'+asset['uid'],headers=v1,json={'name':'3D Object','model_3d':None})
    assert removed.status_code==200,removed.text
    assert 'model_3d' not in removed.json() and not path.exists()

    upload2=c.post('/api/v1/asset/'+asset['uid'],headers=v1,data={'name':'3D Object'},files={'model_3d':('box2.glb',glb_bytes(),'model/gltf-binary')})
    assert upload2.status_code==200,upload2.text
    path2=Path(tmp_path/'media'/Path(upload2.json()['model_3d']).name); assert path2.is_file()
    assert c.delete('/api/v1/asset/'+asset['uid'],headers=v1).status_code==200
    assert not path2.exists()


def test_v2_asset_multipart_path(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    r=c.post('/api/v2/assets',headers=v2,data={'name':'Native Asset'},files={'model_3d':('native.glb',glb_bytes(),'model/gltf-binary')})
    assert r.status_code==200,r.text
    body=r.json(); assert body['kind']=='asset' and body['model_3d'].startswith('/media/')
    uid=body['uid']
    r=c.put('/api/v2/assets/'+uid,headers=v2,json={'mass':2.5,'linear_damping':0.2})
    assert r.status_code==200,r.text
    assert r.json()['mass']==2.5 and r.json()['linear_damping']==0.2


def test_polycam_data_without_raw_glb_preserves_existing_map(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    created=c.post('/api/v1/scene',headers=v1,data={'name':'CalibMesh','output_lla':'false'},files={'map':('CalibMesh.glb',glb_bytes(),'model/gltf-binary')})
    assert created.status_code==201,created.text
    before=created.json(); old_map=before['map']; old_thumb=before['thumbnail']
    dataset=io.BytesIO()
    with zipfile.ZipFile(dataset,'w') as z:
        z.writestr('demo/mesh_info.json','{}')
        z.writestr('demo/keyframes/images/1.jpg',b'x')
        z.writestr('demo/keyframes/depth/1.png',b'x')
        z.writestr('demo/keyframes/cameras/1.json','{}')
    updated=c.post('/api/v1/scene/'+before['uid'],headers=v1,data={},files={'polycam_data':('calibration.zip',dataset.getvalue(),'application/zip')})
    assert updated.status_code==200,updated.text
    value=updated.json()
    assert value['map']==old_map
    assert value['polycam_data'].endswith('.zip')
    assert value['camera_calibration']=='Manual'
    assert value['thumbnail']!=old_thumb
    assert not (tmp_path/'media'/Path(old_thumb).name).exists()


def test_native_scene_export_contains_json_and_map(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    created=c.post('/api/v2/scenes',headers=v2,json={'uid':'export-scene','name':'Export Scene','scale':100})
    assert created.status_code==200,created.text
    uploaded=c.post('/api/v2/scenes/export-scene/files',headers=v2,data={},files={'map':('floor.png',png_bytes(),'image/png')})
    assert uploaded.status_code==200,uploaded.text
    exported=c.get('/api/v2/scenes/export-scene/export',headers=v2)
    assert exported.status_code==200
    assert exported.headers['content-type'].startswith('application/zip')
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        names=archive.namelist()
        assert any(name.endswith('.json') for name in names)
        assert any(name.endswith('.png') for name in names)
        scene=json.loads(archive.read(next(name for name in names if name.endswith('.json'))))
        assert scene['uid']=='export-scene' and scene['map'].startswith('/media/')


def test_native_mapping_routes_delegate_and_finalize_notifications(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    assert c.post('/api/v2/scenes',headers=v2,json={'uid':'mesh-scene','name':'Mesh'}).status_code==200
    import scenescape_api.app as app_module
    monkeypatch.setattr(app_module,'mapping_health',lambda:{'available':True,'ready':True})
    monkeypatch.setattr(app_module,'start_mesh_generation',lambda db,scene_id,p,mesh_type='mesh',video=None:{'success':True,'request_id':'r1'})
    monkeypatch.setattr(app_module,'mesh_generation_status',lambda db,scene_id,request_id,p:{
        'success':True,'state':'complete','finalized':True,
        '_before_scene':{'name':'Mesh'},'_after_scene':{'name':'Mesh','map':'/media/generated.glb'},
        '_changed_cameras':[]
    })
    assert c.get('/api/v2/mapping/health',headers=v2).json()['ready'] is True
    started=c.post('/api/v2/scenes/mesh-scene/mesh',headers=v2,data={'mesh_type':'mesh'})
    assert started.status_code==200 and started.json()['request_id']=='r1'
    status=c.get('/api/v2/scenes/mesh-scene/mesh/status?request_id=r1',headers=v2)
    assert status.status_code==200 and status.json()['finalized'] is True


def test_generated_mesh_connectivity_guard_matches_2026_2():
    import numpy as np
    import trimesh
    from scenescape_api.mapping_service import _check_mesh_connectivity

    first=trimesh.creation.box(extents=[2.0,2.0,1.0])
    second=trimesh.creation.box(extents=[2.0,2.0,1.0])
    second.apply_translation([20.0,0.0,0.0])
    disconnected=trimesh.util.concatenate([first,second])
    error=_check_mesh_connectivity(disconnected)
    assert error is not None and 'spatially separate surfaces' in error

    joined=trimesh.creation.box(extents=[4.0,2.0,1.0])
    assert _check_mesh_connectivity(joined) is None


def test_geospatial_snapshot_legacy_and_native_routes(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    encoded=base64.b64encode(png_bytes()).decode()
    for path in ('/api/v1/save-geospatial-snapshot/','/api/v2/geospatial/snapshot'):
        response=c.post(path,headers=v2,json={'image_data':'data:image/png;base64,'+encoded})
        assert response.status_code==200,response.text
        body=response.json()
        assert body['success'] is True and body['media_url'].startswith('/media/')
        assert (tmp_path/'media'/body['filename']).is_file()


def test_legacy_mapping_route_aliases(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    assert c.post('/api/v2/scenes',headers=v2,json={'uid':'alias-scene','name':'Alias'}).status_code==200
    import scenescape_api.app as app_module
    monkeypatch.setattr(app_module,'mapping_health',lambda:{'available':True,'ready':True})
    monkeypatch.setattr(app_module,'start_mesh_generation',lambda db,scene_id,p,mesh_type='mesh',video=None:{'success':True,'request_id':'alias-r1'})
    monkeypatch.setattr(app_module,'mesh_generation_status',lambda db,scene_id,request_id,p:{
        'success':True,'state':'complete','finalized':False
    })
    assert c.get('/mapping-service/status/',headers=v2).json()['ready'] is True
    started=c.post('/scene/generate-mesh/alias-scene/',headers=v2,data={'mesh_type':'mesh'})
    assert started.status_code==200 and started.json()['request_id']=='alias-r1'
    status=c.get('/scene/generate-mesh-status/alias-scene/?request_id=alias-r1',headers=v2)
    assert status.status_code==200 and status.json()['state']=='complete'


def test_asset_validation_matches_2026_2_choices(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    created=c.post('/api/v2/assets',headers=v2,json={
        'name':'Vehicle',
        'project_to_map':False,
        'rotation_from_velocity':True,
        'is_static':False,
        'shift_type':2,
        'x_size':2.0,'y_size':1.0,'z_size':1.5,
        'tracking_radius':3.0,
        'geometric_center':[0,0,0.75],
        'center_of_mass':[0,0,0.6],
        'friction_coefficients':[0.6,0.4],
    })
    assert created.status_code==200,created.text
    body=created.json()
    assert body['project_to_map'] is False
    assert body['rotation_from_velocity'] is True
    assert body['is_static'] is False
    assert body['shift_type']==2
    assert body['geometric_center']==[0.0,0.0,0.75]

    updated=c.put(
        f"/api/v2/assets/{body['uid']}?revision={body['revision']}",
        headers=v2,
        data={
            'project_to_map':'true',
            'rotation_from_velocity':'false',
            'is_static':'true',
            'shift_type':'1',
        },
    )
    assert updated.status_code==200,updated.text
    value=updated.json()
    assert value['project_to_map'] is True
    assert value['rotation_from_velocity'] is False
    assert value['is_static'] is True
    assert value['shift_type']==1

    assert c.post('/api/v2/assets',headers=v2,json={'name':'Bad shift','shift_type':3}).status_code==400
    assert c.post('/api/v2/assets',headers=v2,json={'name':'Bad bool','project_to_map':'not-bool'}).status_code==400
    assert c.post('/api/v2/assets',headers=v2,json={'name':'Bad damping','linear_damping':1.5}).status_code==400


def test_native_asset_model_replacement_and_removal(tmp_path,monkeypatch):
    c,d,v1,v2,calls=boot(tmp_path,monkeypatch)
    first=c.post('/api/v2/assets',headers=v2,data={'name':'Forklift'},files={'model_3d':('forklift.glb',glb_bytes(),'model/gltf-binary')})
    assert first.status_code==200,first.text
    value=first.json()
    first_path=tmp_path/'media'/Path(value['model_3d']).name
    assert first_path.is_file()

    replacement=c.put(
        f"/api/v2/assets/{value['uid']}?revision={value['revision']}",
        headers=v2,data={'name':'Forklift'},files={'model_3d':('forklift-v2.glb',glb_bytes(),'model/gltf-binary')}
    )
    assert replacement.status_code==200,replacement.text
    second=replacement.json()
    second_path=tmp_path/'media'/Path(second['model_3d']).name
    assert second_path.is_file() and not first_path.exists()

    removed=c.put(
        f"/api/v2/assets/{second['uid']}?revision={second['revision']}",
        headers=v2,json={'model_3d':None}
    )
    assert removed.status_code==200,removed.text
    assert removed.json().get('model_3d') is None
    assert not second_path.exists()
