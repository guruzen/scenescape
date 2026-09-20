import pytest
from fastapi import HTTPException


def actor():
    from scenescape_api.auth import Principal
    return Principal('tester','Tester',frozenset({'scenescape-admin'}),frozenset({'*'}),9999999999)


def make_db(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path}/hierarchy.db')
    import scenescape_api.database as d
    if d._engine is not None:
        d._engine.dispose()
    d._engine=None; d._Session=None
    d.Base.metadata.create_all(d.get_engine())
    return d


def scene(db, uid, name=None):
    from scenescape_api.resources import upsert
    with db.sessions()() as session:
        row=upsert(session,'scene',uid,{'name':name or uid},actor()); session.commit(); return row.uid


def link(db, body, legacy=True):
    from scenescape_api.hierarchy import create_child_link
    with db.sessions()() as session:
        row=create_child_link(session,body,actor(),legacy=legacy); session.commit(); return row.uid


def test_local_child_defaults_and_representation(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A','Parent'); scene(d,'B','Child')
    uid=link(d,{'child_type':'local','parent':'A','child':'B'})
    assert uid.isdigit()
    from scenescape_api.hierarchy import child_to_dict, resolve_child_link
    with d.sessions()() as db:
        value=child_to_dict(db,resolve_child_link(db,uid))
    assert value['uid']==uid
    assert value['name']=='Child'
    assert value['child_type']=='local'
    assert value['parent']=='A' and value['child']=='B'
    assert value['retrack'] is True and value['transform_type']=='matrix'
    assert value['transform']=={'translation':[0.0,0.0,0.0],'rotation':[0.0,0.0,0.0],'scale':[1.0,1.0,1.0]}
    assert [value[f'transform{i}'] for i in range(1,17)]==[1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0]
    assert 'cached_rois' not in value and 'cached_tripwires' not in value


def test_self_duplicate_and_one_parent_are_rejected(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    for x in 'ABC': scene(d,x)
    from scenescape_api.hierarchy import create_child_link
    with d.sessions()() as db:
        with pytest.raises(HTTPException): create_child_link(db,{'child_type':'local','parent':'A','child':'A'},actor(),legacy=True)
    link(d,{'child_type':'local','parent':'A','child':'B'})
    with d.sessions()() as db:
        with pytest.raises(HTTPException): create_child_link(db,{'child_type':'local','parent':'A','child':'B'},actor(),legacy=True)
        with pytest.raises(HTTPException): create_child_link(db,{'child_type':'local','parent':'C','child':'B'},actor(),legacy=True)


def test_direct_and_transitive_cycles_are_rejected(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    for x in 'ABC': scene(d,x)
    link(d,{'child_type':'local','parent':'A','child':'B'})
    from scenescape_api.hierarchy import create_child_link
    with d.sessions()() as db:
        with pytest.raises(HTTPException): create_child_link(db,{'child_type':'local','parent':'B','child':'A'},actor(),legacy=True)
    link(d,{'child_type':'local','parent':'B','child':'C'})
    with d.sessions()() as db:
        with pytest.raises(HTTPException): create_child_link(db,{'child_type':'local','parent':'C','child':'A'},actor(),legacy=True)


def test_valid_chain_tree_and_reparent(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    for x in 'ABCDE': scene(d,x)
    b=link(d,{'child_type':'local','parent':'A','child':'B'})
    link(d,{'child_type':'local','parent':'B','child':'C'})
    link(d,{'child_type':'local','parent':'A','child':'D'})
    from scenescape_api.hierarchy import resolve_child_link, update_child_link, child_to_dict
    with d.sessions()() as db:
        row=resolve_child_link(db,b)
        row,notify=update_child_link(db,row,{'child_type':'local','parent':'E','child':'B'},actor(),legacy=True)
        db.commit(); value=child_to_dict(db,row)
    assert notify is True and value['parent']=='E'


def test_reparent_that_creates_cycle_is_rejected(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    for x in 'ABC': scene(d,x)
    b=link(d,{'child_type':'local','parent':'A','child':'B'})
    link(d,{'child_type':'local','parent':'B','child':'C'})
    from scenescape_api.hierarchy import resolve_child_link, update_child_link
    with d.sessions()() as db:
        row=resolve_child_link(db,b)
        with pytest.raises(HTTPException): update_child_link(db,row,{'child_type':'local','parent':'C','child':'B'},actor(),legacy=True)


def test_resolve_accepts_link_uid_or_child_scene_uid(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A'); scene(d,'B')
    uid=link(d,{'child_type':'local','parent':'A','child':'B'})
    from scenescape_api.hierarchy import resolve_child_link
    with d.sessions()() as db:
        assert resolve_child_link(db,uid).uid==uid
        assert resolve_child_link(db,'B').uid==uid
        with pytest.raises(HTTPException): resolve_child_link(db,'missing')


def test_cache_only_update_preserves_link_and_skips_notify(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A'); scene(d,'B')
    uid=link(d,{'child_type':'local','parent':'A','child':'B'})
    from scenescape_api.hierarchy import resolve_child_link, update_child_link, child_to_dict
    with d.sessions()() as db:
        row=resolve_child_link(db,uid)
        row,notify=update_child_link(db,row,{'cached_rois':[{'name':'z'}]},actor(),legacy=True)
        db.commit(); native=child_to_dict(db,row,native=True)
    assert notify is False
    assert native['parent']=='A' and native['child']=='B'
    assert native['cached_rois']==[{'name':'z'}]


def test_remote_required_unique_and_euler_transform(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A'); scene(d,'B')
    remote='11111111-1111-4111-8111-111111111111'
    body={'child_type':'remote','parent':'A','remote_child_id':remote,'child_name':'Remote','host_name':'broker','mqtt_username':'u','mqtt_password':'p','transform_type':'euler','transform1':10,'transform2':20,'transform3':3,'transform4':1,'transform5':2,'transform6':3,'transform7':2,'transform8':2,'transform9':2}
    uid=link(d,body)
    from scenescape_api.hierarchy import child_to_dict, create_child_link, resolve_child_link
    with d.sessions()() as db:
        value=child_to_dict(db,resolve_child_link(db,uid))
        assert value['name']=='Remote' and 'child' not in value
        assert value['transform']=={'translation':[10.0,20.0,3.0],'rotation':[1.0,2.0,3.0],'scale':[2.0,2.0,2.0]}
        with pytest.raises(HTTPException): create_child_link(db,{'child_type':'remote','parent':'B','remote_child_id':remote,'child_name':'Other','host_name':'x','mqtt_username':'u','mqtt_password':'p'},actor(),legacy=True)
        with pytest.raises(HTTPException): create_child_link(db,{'child_type':'remote','parent':'A'},actor(),legacy=True)


def test_local_update_clears_remote_only_fields(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A'); scene(d,'B')
    remote='22222222-2222-4222-8222-222222222222'
    uid=link(d,{'child_type':'remote','parent':'A','remote_child_id':remote,'child_name':'Remote','host_name':'broker','mqtt_username':'u','mqtt_password':'p'})
    from scenescape_api.hierarchy import resolve_child_link, update_child_link
    with d.sessions()() as db:
        row=resolve_child_link(db,uid)
        row,_=update_child_link(db,row,{'child_type':'local','parent':'A','child':'B'},actor(),legacy=True)
        db.commit(); payload=row.payload
    assert payload['child']=='B'
    assert all(payload.get(field) is None for field in ('remote_child_id','child_name','host_name','mqtt_username','mqtt_password'))


def test_scene_delete_cascade_removes_incoming_and_outgoing_links_only(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    for x in 'ABCD': scene(d,x)
    link(d,{'child_type':'local','parent':'A','child':'B'})
    link(d,{'child_type':'local','parent':'B','child':'C'})
    link(d,{'child_type':'local','parent':'A','child':'D'})
    from scenescape_api.hierarchy import cascade_scene_links
    from scenescape_api.resources import list_resources
    with d.sessions()() as db:
        deleted=cascade_scene_links(db,'B'); db.commit()
        children=list_resources(db,'child')
    assert len(deleted)==2
    assert len(children)==1 and children[0]['child']=='D'


def test_remote_id_cannot_equal_parent_and_must_be_uuid(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch)
    parent='33333333-3333-4333-8333-333333333333'; scene(d,parent)
    from scenescape_api.hierarchy import create_child_link
    base={'child_type':'remote','parent':parent,'child_name':'Remote','host_name':'broker','mqtt_username':'u','mqtt_password':'p'}
    with d.sessions()() as db:
        with pytest.raises(HTTPException): create_child_link(db,{**base,'remote_child_id':parent},actor(),legacy=True)
        with pytest.raises(HTTPException): create_child_link(db,{**base,'remote_child_id':'not-a-uuid'},actor(),legacy=True)


def test_nested_migration_assigns_child_parent_not_scene():
    from scenescape_api.migrate_legacy import normalize_snapshot
    snapshot=normalize_snapshot({'uid':'A','name':'Parent','children':[{'uid':'link-1','child_type':'remote','remote_child_id':'11111111-1111-4111-8111-111111111111','child_name':'Remote','host_name':'broker','mqtt_username':'u','mqtt_password':'p'}]})
    assert snapshot['children'][0]['parent']=='A'
    assert 'scene' not in snapshot['children'][0]


def test_local_create_rejects_child_name_model_constraint(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A'); scene(d,'B')
    from scenescape_api.hierarchy import create_child_link
    with d.sessions()() as db:
        with pytest.raises(HTTPException):
            create_child_link(db,{'child_type':'local','parent':'A','child':'B','child_name':'conflict'},actor(),legacy=True)


def test_pre_1c_scene_parent_artifact_is_read_and_canonicalized(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A'); scene(d,'B'); scene(d,'C')
    from scenescape_api.resources import upsert
    from scenescape_api.hierarchy import child_to_dict, resolve_child_link, update_child_link, cascade_scene_links
    with d.sessions()() as db:
        row=upsert(db,'child','legacy-link',{'child_type':'local','scene':'A','child':'B'},actor()); db.commit()
        value=child_to_dict(db,row)
        assert value['parent']=='A' and 'scene' not in value
        row,_=update_child_link(db,row,{'child_type':'local','parent':'C','child':'B'},actor(),legacy=True)
        db.commit()
        assert row.payload['parent']=='C'
        assert 'scene' not in row.payload
        assert resolve_child_link(db,'B').uid=='legacy-link'
        assert cascade_scene_links(db,'C')==['legacy-link']


def test_retrack_false_and_quaternion_transform_are_preserved(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A'); scene(d,'B')
    from scenescape_api.hierarchy import create_child_link, child_to_dict
    with d.sessions()() as db:
        row=create_child_link(db,{
            'child_type':'local','parent':'A','child':'B','retrack':False,
            'transform':{
                'translation':[1,2,3],
                'rotation':[0,0,0,1],
                'scale':[1.5,1.5,1.5],
            },
        },actor(),legacy=False)
        db.commit()
        value=child_to_dict(db,row,native=True)
    assert value['retrack'] is False
    assert value['transform_type']=='quaternion'
    assert value['transform']['translation']==[1.0,2.0,3.0]
    assert value['transform']['rotation']==pytest.approx([0.0,0.0,0.0])
    assert value['transform']['scale']==[1.5,1.5,1.5]
    assert [value[f'transform{i}'] for i in range(4,8)]==[0.0,0.0,0.0,1.0]


def test_retrack_string_false_is_not_coerced_true(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A'); scene(d,'B')
    from scenescape_api.hierarchy import create_child_link, child_to_dict
    with d.sessions()() as db:
        row=create_child_link(db,{'child_type':'local','parent':'A','child':'B','retrack':'false'},actor(),legacy=False)
        db.commit()
        value=child_to_dict(db,row,native=True)
    assert value['retrack'] is False


def test_child_matrix_transform_round_trip(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A'); scene(d,'B')
    from scenescape_api.hierarchy import create_child_link, child_to_dict
    matrix=[
        1,0,0,10,
        0,1,0,20,
        0,0,1,30,
        0,0,0,1,
    ]
    body={'child_type':'local','parent':'A','child':'B','transform_type':'matrix'}
    body.update({f'transform{i+1}':value for i,value in enumerate(matrix)})
    with d.sessions()() as db:
        row=create_child_link(db,body,actor(),legacy=False); db.commit()
        value=child_to_dict(db,row,native=True)
    assert value['transform_type']=='matrix'
    assert value['transform']['translation']==[10.0,20.0,30.0]
    assert value['transform']['scale']==pytest.approx([1.0,1.0,1.0])
    assert [value[f'transform{i}'] for i in range(1,17)]==[float(x) for x in matrix]


def test_invalid_retrack_value_is_rejected(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A'); scene(d,'B')
    from scenescape_api.hierarchy import create_child_link
    with d.sessions()() as db:
        with pytest.raises(HTTPException):
            create_child_link(db,{'child_type':'local','parent':'A','child':'B','retrack':'sometimes'},actor(),legacy=False)


def test_native_remote_password_is_write_only_and_blank_update_preserves_secret(tmp_path, monkeypatch):
    d=make_db(tmp_path,monkeypatch); scene(d,'A')
    remote='44444444-4444-4444-8444-444444444444'
    uid=link(d,{
        'child_type':'remote','parent':'A','remote_child_id':remote,
        'child_name':'Remote','host_name':'broker','mqtt_username':'u','mqtt_password':'secret'
    })
    from scenescape_api.hierarchy import child_to_dict, resolve_child_link, update_child_link
    with d.sessions()() as db:
        row=resolve_child_link(db,uid)
        native=child_to_dict(db,row,native=True)
        assert 'mqtt_password' not in native
        assert native['has_mqtt_password'] is True
        row,_=update_child_link(db,row,{
            'child_type':'remote','parent':'A','remote_child_id':remote,
            'child_name':'Remote','host_name':'broker2','mqtt_username':'u2','mqtt_password':''
        },actor(),legacy=False)
        db.commit()
        assert row.payload['mqtt_password']=='secret'
        native=child_to_dict(db,row,native=True)
        assert 'mqtt_password' not in native and native['has_mqtt_password'] is True
