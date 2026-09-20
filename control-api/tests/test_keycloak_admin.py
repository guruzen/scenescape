import pytest
from fastapi import HTTPException


def test_scene_scope_claim_normalizes_single_string():
    from scenescape_api.auth import _principal
    principal=_principal({
        'sub':'viewer','preferred_username':'viewer','roles':['scenescape-viewer'],
        'scenes':'scene-1','exp':9999999999,
    })
    assert principal.scene_scopes==frozenset({'scene-1'})


def test_mqtt_topic_matching_and_acl_access(monkeypatch):
    import scenescape_api.keycloak_admin as admin
    admin._clear_acl_cache()
    monkeypatch.setattr(admin,'_get_user_rep',lambda username:{
        'id':'u1','username':username,
        'attributes':{
            admin.ACL_ATTRIBUTE:[
                '{"topic":"DATA_SCENE","access":1}',
                '{"topic":"CMD_CAMERA","access":3}',
            ]
        },
    })
    monkeypatch.setattr(admin,'_realm_roles_for_user',lambda user_id:[{'name':'scenescape-viewer'}])

    allowed,access=admin.acl_check('viewer','scenescape/data/scene/scene-a/person',1)
    assert allowed is True and access==1
    allowed,access=admin.acl_check('viewer','scenescape/data/scene/scene-a/person',4)
    assert allowed is True and access==4
    allowed,access=admin.acl_check('viewer','scenescape/cmd/camera/cam-1',2)
    assert allowed is True and access==2
    denied,_=admin.acl_check('viewer','scenescape/cmd/database',2)
    assert denied is False


def test_admin_role_has_full_mqtt_access(monkeypatch):
    import scenescape_api.keycloak_admin as admin
    admin._clear_acl_cache()
    monkeypatch.setattr(admin,'_get_user_rep',lambda username:{'id':'admin-1','username':username,'attributes':{}})
    monkeypatch.setattr(admin,'_realm_roles_for_user',lambda user_id:[{'name':'scenescape-admin'}])
    assert admin.acl_check('admin','any/topic',2)==(True,3)


def test_acl_validation_rejects_unknown_topics_and_duplicates():
    import scenescape_api.keycloak_admin as admin
    with pytest.raises(HTTPException):
        admin._normalize_acls([{'topic':'UNKNOWN','access':1}])
    with pytest.raises(HTTPException):
        admin._normalize_acls([
            {'topic':'DATA_SCENE','access':1},
            {'topic':'DATA_SCENE','access':2},
        ])


def test_topic_templates_match_tagged_shapes():
    import scenescape_api.keycloak_admin as admin
    assert admin.match_topic(admin.TOPIC_TEMPLATES['DATA_SENSOR'],'scenescape/data/sensor/temp-1')
    assert admin.match_topic(admin.TOPIC_TEMPLATES['EVENT'],'scenescape/event/region/scene-1/roi-1/occupancy')
    assert not admin.match_topic(admin.TOPIC_TEMPLATES['DATA_SENSOR'],'scenescape/data/scene/temp-1/person')


def test_service_identity_acl_policy(tmp_path, monkeypatch):
    import json
    import scenescape_api.keycloak_admin as admin
    controller=tmp_path/'controller.auth'
    browser=tmp_path/'browser.auth'
    calibration=tmp_path/'calibration.auth'
    controller.write_text(json.dumps({'user':'scenectrl','password':'secret'}))
    browser.write_text(json.dumps({'user':'webuser','password':'secret'}))
    calibration.write_text(json.dumps({'user':'calibration','password':'secret'}))
    monkeypatch.setenv('SERVICE_AUTH_FILES',f'{controller}:{browser}:{calibration}')

    identities={item['username']:item for item in admin.list_service_identities()}
    assert set(identities)=={'scenectrl','webuser','calibration'}
    assert identities['scenectrl']['service_type']=='controller'
    assert identities['webuser']['service_type']=='browser'

    assert admin.service_acl_check('scenectrl','scenescape/cmd/camera/cam-1',2)==(True,2)
    assert admin.service_acl_check('scenectrl','scenescape/regulated/scene/scene-1',1)==(False,None)
    assert admin.service_acl_check('calibration','scenescape/autocalibration/camera/pose/cam-1',2)==(True,2)
    assert admin.service_acl_check('webuser','scenescape/data/camera/cam-1',4)==(True,4)
    assert admin.service_acl_check('unknown','scenescape/data/camera/cam-1',1) is None


def test_service_acl_policy_exactly_matches_2026_2_user_access_config(tmp_path, monkeypatch):
    import json
    import scenescape_api.keycloak_admin as admin
    controller=tmp_path/'controller.auth'
    browser=tmp_path/'browser.auth'
    calibration=tmp_path/'calibration.auth'
    controller.write_text(json.dumps({'user':'scenectrl','password':'secret'}))
    browser.write_text(json.dumps({'user':'webuser','password':'secret'}))
    calibration.write_text(json.dumps({'user':'calibration','password':'secret'}))
    monkeypatch.setenv('SERVICE_AUTH_FILES',f'{controller}:{browser}:{calibration}')

    expected={
      'controller': [
        ('CMD_CAMERA',3),('IMAGE_CALIBRATE',1),('CMD_DATABASE',3),('DATA_REGULATED',2),
        ('DATA_SCENE',2),('DATA_AUTOCALIB_CAM_POSE',2),('CMD_KUBECLIENT',3),
        ('CMD_SCENE_UPDATE',3),('DATA_EXTERNAL',3),('DATA_REGION',2),('DATA_SENSOR',1),
        ('EVENT',3),('SYS_CHILDSCENE_STATUS',3),('DATA_CAMERA',1),
      ],
      'browser': [
        ('DATA_CAMERA',1),('CHANNEL',1),('IMAGE_CAMERA',1),('IMAGE_CALIBRATE',1),
        ('CMD_DATABASE',3),('CMD_CAMERA',3),('DATA_AUTOCALIB_CAM_POSE',1),
        ('CMD_KUBECLIENT',3),('EVENT',1),('SYS_CHILDSCENE_STATUS',3),
        ('DATA_REGULATED',1),('DATA_EXTERNAL',1),
      ],
      'calibration': [
        ('IMAGE_CALIBRATE',1),('CMD_SCENE_UPDATE',1),('DATA_AUTOCALIB_CAM_POSE',2),
      ],
    }
    identities={item['service_type']:item for item in admin.list_service_identities()}
    assert set(identities)==set(expected)
    for service_type, policy in expected.items():
        assert [(item['topic'],item['access']) for item in identities[service_type]['acls']]==policy


def test_keycloak_user_projection_preserves_legacy_privilege_flags_and_native_scopes(monkeypatch):
    import scenescape_api.keycloak_admin as admin
    monkeypatch.setattr(admin,'_realm_roles_for_user',lambda user_id:[
        {'name':'scenescape-viewer'},{'name':'scenescape-admin'}
    ])
    rep={
      'id':'u1','username':'operator','enabled':False,
      'firstName':'Scene','lastName':'Operator','email':'scene@example.test',
      'attributes':{
        admin.SCENE_ATTRIBUTE:['scene-a','scene-b'],
        admin.ACL_ATTRIBUTE:['{"topic":"DATA_SCENE","access":1}'],
      },
    }
    value=admin.user_to_dict(rep)
    assert value['is_active'] is False
    assert value['is_staff'] is True and value['is_superuser'] is True
    assert value['roles']==['scenescape-admin','scenescape-viewer']
    assert value['scenes']==['scene-a','scene-b']
    assert value['acls']==[{'topic':'DATA_SCENE','access':1}]
