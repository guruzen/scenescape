import json
from fastapi.testclient import TestClient


def boot(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/hier-api.db')
    monkeypatch.setenv('API_SIGNING_KEY','test-signing-key-abcdefghijklmnopqrstuvwxyz')
    auth=tmp_path/'service.json'; auth.write_text(json.dumps({'user':'svc','password':'pw'})); monkeypatch.setenv('SERVICE_AUTH_FILES',str(auth))
    import scenescape_api.database as d
    if d._engine is not None: d._engine.dispose()
    d._engine=None; d._Session=None
    import scenescape_api.app as a
    monkeypatch.setattr(a,'notify_config_change',lambda kind,uid=None:{'ok':True})
    monkeypatch.setattr(a,'notify_camera_change',lambda *a,**k:{'ok':True})
    d.Base.metadata.create_all(d.get_engine())
    c=TestClient(a.app)
    token=c.post('/api/v1/auth',data={'username':'svc','password':'pw'}).json()['token']
    return c, {'Authorization':'Bearer '+token}


def add_scenes(c,h,*ids):
    for uid in ids:
        r=c.post('/api/v2/scenes',headers=h,json={'uid':uid,'name':uid})
        assert r.status_code==200, r.text


def test_hierarchy_api_scenarios_19_to_30_core(tmp_path,monkeypatch):
    c,h=boot(tmp_path,monkeypatch); add_scenes(c,h,'A','B','C','D')
    ab=c.post('/api/v2/children',headers=h,json={'child_type':'local','parent':'A','child':'B'})
    assert ab.status_code==200,ab.text; link=ab.json()['uid']
    assert ab.json()['transform']['translation']==[0.0,0.0,0.0]
    assert c.post('/api/v2/children',headers=h,json={'child_type':'local','parent':'B','child':'A'}).status_code==400
    bc=c.post('/api/v2/children',headers=h,json={'child_type':'local','parent':'B','child':'C'})
    assert bc.status_code==200
    assert c.post('/api/v2/children',headers=h,json={'child_type':'local','parent':'C','child':'A'}).status_code==400
    assert c.post('/api/v2/children',headers=h,json={'child_type':'local','parent':'A','child':'B'}).status_code==400
    # Reparent B to C would cycle through B->C; reject.
    assert c.put('/api/v2/children/B',headers=h,json={'child_type':'local','parent':'C','child':'B'}).status_code==400
    # Remove B->C, then reparent B from A to D using the child Scene UUID fallback.
    assert c.delete('/api/v2/children/C',headers=h).status_code==200
    moved=c.put('/api/v2/children/B',headers=h,json={'child_type':'local','parent':'D','child':'B'})
    assert moved.status_code==200 and moved.json()['uid']==link and moved.json()['parent']=='D'


def test_hierarchy_cache_only_update_has_no_config_notify(tmp_path,monkeypatch):
    c,h=boot(tmp_path,monkeypatch); add_scenes(c,h,'A','B')
    import scenescape_api.app as a
    calls=[]; monkeypatch.setattr(a,'notify_config_change',lambda kind,uid=None:calls.append((kind,uid)) or {'ok':True})
    row=c.post('/api/v2/children',headers=h,json={'parent':'A','child':'B'}).json(); calls.clear()
    updated=c.put(f"/api/v2/children/{row['uid']}",headers=h,json={'cached_rois':[{'name':'zone'}]})
    assert updated.status_code==200 and updated.json()['cached_rois']==[{'name':'zone'}]
    assert calls==[]


def test_scene_delete_cascades_hierarchy_links(tmp_path,monkeypatch):
    c,h=boot(tmp_path,monkeypatch); add_scenes(c,h,'A','B','C')
    assert c.post('/api/v2/children',headers=h,json={'parent':'A','child':'B'}).status_code==200
    assert c.post('/api/v2/children',headers=h,json={'parent':'B','child':'C'}).status_code==200
    assert len(c.get('/api/v2/children',headers=h).json())==2
    assert c.delete('/api/v2/scenes/B',headers=h).status_code==200
    assert c.get('/api/v2/children',headers=h).json()==[]


def test_remote_child_api_contract(tmp_path,monkeypatch):
    c,h=boot(tmp_path,monkeypatch); add_scenes(c,h,'A')
    remote='11111111-1111-4111-8111-111111111111'
    r=c.post('/api/v2/children',headers=h,json={'child_type':'remote','parent':'A','remote_child_id':remote,'child_name':'Remote','host_name':'broker','mqtt_username':'u','mqtt_password':'p','transform_type':'euler','transform1':1,'transform2':2,'transform3':3,'transform4':0,'transform5':0,'transform6':0,'transform7':1,'transform8':1,'transform9':1})
    assert r.status_code==200,r.text
    body=r.json(); assert body['name']=='Remote' and body['transform']['translation']==[1.0,2.0,3.0]
    assert c.get('/api/v2/children/'+remote,headers=h).status_code==200


def test_v1_hierarchy_representation_and_child_uuid_fallback(tmp_path,monkeypatch):
    c,admin=boot(tmp_path,monkeypatch); add_scenes(c,admin,'A','B')
    service=c.post('/api/v1/auth',data={'username':'svc','password':'pw'})
    h={'Authorization':'Token '+service.json()['token']}
    created=c.post('/api/v1/child',headers=h,json={'child_type':'local','parent':'A','child':'B'})
    assert created.status_code==201,created.text
    link=created.json()['uid']
    listing=c.get('/api/v1/scenes/child',headers=h)
    assert listing.status_code==200 and listing.json()['count']==1
    row=listing.json()['results'][0]
    assert row['uid']==link and row['name']=='B' and row['parent']=='A' and row['child']=='B'
    assert row['transform']=={'translation':[0.0,0.0,0.0],'rotation':[0.0,0.0,0.0],'scale':[1.0,1.0,1.0]}
    parent=c.get('/api/v1/scene/A',headers=h).json()
    assert parent['children'][0]['uid']=='B'
    assert parent['children'][0]['link']['uid']==link
    assert parent['children'][0]['parent']=='A'
    deleted=c.delete('/api/v1/child/B',headers=h)
    assert deleted.status_code==200
    assert c.get('/api/v1/scenes/child',headers=h).json()['count']==0


def test_v1_2026_2_hierarchy_scenarios_19_through_33(tmp_path,monkeypatch):
    c,admin=boot(tmp_path,monkeypatch)
    service=c.post('/api/v1/auth',data={'username':'svc','password':'pw'})
    h={'Authorization':'Token '+service.json()['token']}

    def new_scene(name):
        r=c.post('/api/v1/scene',headers=h,json={'name':name,'use_tracker':True,'output_lla':False})
        assert r.status_code==201,r.text
        return r.json()['uid']
    A=new_scene('Circular_Dep_Scene_A'); B=new_scene('Circular_Dep_Scene_B')
    C=new_scene('Circular_Dep_Scene_C'); D=new_scene('Circular_Dep_Scene_D')
    def create(parent,child):
        return c.post('/api/v1/child',headers=h,json={'child_type':'local','parent':parent,'child':child})
    def delete(child_or_link):
        return c.delete('/api/v1/child/'+child_or_link,headers=h)
    def count():
        r=c.get('/api/v1/scenes/child',headers=h); assert r.status_code==200; return r.json()['count']

    # 19-21: create, list, delete.
    r=create(A,B); assert r.status_code==201; assert count()==1
    assert delete(B).status_code==200; assert count()==0
    # 22: self reference.
    assert create(A,A).status_code==400
    # 23: direct two-node cycle.
    assert create(A,B).status_code==201; assert create(B,A).status_code==400
    assert delete(B).status_code==200; assert count()==0
    # 24: transitive three-node cycle.
    assert create(A,B).status_code==201; assert create(B,C).status_code==201
    assert create(C,A).status_code==400
    assert delete(C).status_code==200; assert delete(B).status_code==200; assert count()==0
    # 25: duplicate link.
    assert create(A,B).status_code==201; assert create(A,B).status_code==400
    assert delete(B).status_code==200; assert count()==0
    # 26: valid linear chain.
    assert create(A,B).status_code==201; assert create(B,C).status_code==201; assert count()==2
    assert delete(C).status_code==200; assert delete(B).status_code==200; assert count()==0
    # 27-28: valid tree, then prevent C from acquiring a second parent.
    assert create(A,B).status_code==201; assert create(A,C).status_code==201; assert count()==2
    assert create(B,C).status_code==400
    assert delete(C).status_code==200; assert delete(B).status_code==200; assert count()==0
    # 29: updating A->B to C->B would cycle with B->C.
    assert create(A,B).status_code==201; assert create(B,C).status_code==201
    bad=c.post('/api/v1/child/'+B,headers=h,json={'child_type':'local','parent':C,'child':B})
    assert bad.status_code==400
    assert delete(C).status_code==200; assert delete(B).status_code==200; assert count()==0
    # 30: valid parent reassignment A->B to D->B.
    first=create(A,B); assert first.status_code==201; link_uid=first.json()['uid']
    moved=c.post('/api/v1/child/'+B,headers=h,json={'child_type':'local','parent':D,'child':B})
    assert moved.status_code==200 and moved.json()['uid']==link_uid and moved.json()['parent']==D
    assert count()==1; assert delete(B).status_code==200; assert count()==0
    # 31-33: scene deletion and nonexistent resources.
    for scene_id in (A,B,C,D):
        assert c.delete('/api/v1/scene/'+scene_id,headers=h).status_code==200
    assert c.get('/api/v1/scene/'+A,headers=h).status_code==404
    assert c.delete('/api/v1/scene/123',headers=h).status_code==404
    assert c.delete('/api/v1/child/00000000-0000-4000-8000-000000000099',headers=h).status_code==404
