import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

TOOLS = Path(__file__).parents[2] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('native_data', Path(__file__).parents[2] / 'tools/native_data.py')
native_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native_data)
rt = native_data.rt


def prepare(tmp_path, monkeypatch):
    root = tmp_path / 'repo'; root.mkdir()
    monkeypatch.setattr(rt, 'ROOT', root)
    monkeypatch.setattr(rt, 'RUNTIME', root / '.scenescape-runtime')
    monkeypatch.setattr(rt, 'STATE', root / '.scenescape-runtime/native-state.json')
    monkeypatch.setattr(rt, 'CONFIG', root / '.scenescape-modern.env')
    rt.save_state({'mode':'native','installed':True})
    return root


def test_seed_native_data_never_deletes_existing_data(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    run=Mock(); compose=Mock(); monkeypatch.setattr(rt,'run',run); monkeypatch.setattr(rt,'compose',compose)
    native_data.seed_native({'COMPOSE_PROJECT_NAME':'test'})
    assert run.call_args.args[0][:2]==['make','init-sample-data']
    assert compose.call_args.args[1:7]==('run','--rm','-T','--no-deps','web','seed')
    assert '--volumes' not in compose.call_args.args


def test_recover_legacy_data_exports_then_imports_without_volume_deletion(tmp_path, monkeypatch):
    root=prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(rt,'doctor',Mock())
    legacy_config={'services':{'web':{'image':'intel/scenescape-manager:2026.2.0'}}}
    calls=[]
    def fake_compose(config,*args,**kwargs):
        calls.append((args,kwargs))
        if args[:3]==('config','--format','json'):
            return SimpleNamespace(stdout=json.dumps(legacy_config).encode(),returncode=0)
        if kwargs.get('output') is not None:
            payload={'scenes':[{'uid':'s1','name':'Legacy'}], '_migration':{'counts':{'scenes':1}}}
            kwargs['output'].write(json.dumps(payload).encode())
        return SimpleNamespace(stdout=b'',returncode=0)
    monkeypatch.setattr(rt,'compose',fake_compose)
    monkeypatch.setattr(rt,'run',Mock(return_value=SimpleNamespace(returncode=0,stdout=b'')))
    (root/'tools').mkdir(parents=True,exist_ok=True)
    (root/'tools/export_legacy.py').write_text('print("fixture")\n')
    native_data.recover_legacy({'COMPOSE_PROJECT_NAME':'test'})
    assert any(kwargs.get('native') is False and '--entrypoint' in args for args,kwargs in calls)
    assert any(kwargs.get('native') is True and 'scenescape_api.migrate_legacy' in args for args,kwargs in calls)
    assert all('--volumes' not in args for args,_ in calls)
    state=rt.read_state(); assert state['mode']=='native' and state.get('legacy_recovery_snapshot')
