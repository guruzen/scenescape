"""Lifecycle safety checks with subprocesses substituted; no Docker daemon needed."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

spec = importlib.util.spec_from_file_location("native_runtime", Path(__file__).parents[2] / "tools/native_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


@pytest.fixture
def rt(tmp_path, monkeypatch):
    root = tmp_path / "repo"; root.mkdir()
    monkeypatch.setattr(runtime, "ROOT", root)
    monkeypatch.setattr(runtime, "RUNTIME", root / ".scenescape-runtime")
    monkeypatch.setattr(runtime, "STATE", root / ".scenescape-runtime/native-state.json")
    monkeypatch.setattr(runtime, "CONFIG", root / ".scenescape-modern.env")
    realm = root / "modern-ui/keycloak/scenescape-realm.json"; realm.parent.mkdir(parents=True)
    realm.write_text(json.dumps({"clients": [{"clientId": "scenescape-ui", "attributes": {}}]}))
    return runtime


def args(**kwargs):
    return SimpleNamespace(port=None, public_url=None, admin_user=None, jobs=2, skip_processing_build=True, yes=True, **kwargs)


def test_fresh_configuration_is_native_and_secret(rt, capsys):
    config = rt.configure(args())
    assert rt.read_state()["mode"] == "native"
    assert rt.CONFIG.stat().st_mode & 0o777 == 0o600
    assert config["KEYCLOAK_ADMIN_PASSWORD"] not in capsys.readouterr().out
    assert rt.load_config()["SCENESCAPE_API_SIGNING_KEY"] == config["SCENESCAPE_API_SIGNING_KEY"]


def test_existing_configuration_requires_explicit_migration(rt):
    rt.CONFIG.write_text("SUPASS=old\nKEYCLOAK_ADMIN_USERNAME=admin\nKEYCLOAK_ADMIN_PASSWORD=keep-this\nSCENESCAPE_PUBLIC_URL=http://localhost:8088\nMODERN_UI_PORT=8088\n")
    config = rt.configure(args())
    assert rt.read_state()["mode"] == "legacy"
    assert config["KEYCLOAK_ADMIN_PASSWORD"] == "keep-this"


@pytest.mark.parametrize("value", ["http://example.com:8088", "http://localhost:8088/path", "http://user:secret@localhost:8088", "https://example.com?x=1"])
def test_invalid_or_insecure_origins_are_rejected(rt, value):
    with pytest.raises(RuntimeError):
        rt.origin(value, 8088)


def test_uninstall_does_not_call_global_cleanup(rt, monkeypatch):
    rt.save_state({"mode": "native", "installed": True})
    compose = Mock(); monkeypatch.setattr(rt, "compose", compose)
    rt.uninstall({"COMPOSE_PROJECT_NAME": "test"}, args())
    assert compose.call_args.args[1:] == ("down", "--volumes", "--remove-orphans")
    assert rt.read_state()["installed"] is False


def test_failed_cutover_restores_legacy_without_deleting_volumes(rt, monkeypatch):
    rt.save_state({"mode": "legacy", "installed": True})
    directory = rt.RUNTIME / "backups/example"; directory.mkdir(parents=True)
    (directory / "legacy-snapshot.json").write_text('{"scenes": []}')
    monkeypatch.setattr(rt, "doctor", Mock())
    monkeypatch.setattr(rt, "build", Mock())
    monkeypatch.setattr(rt, "run", Mock(return_value=SimpleNamespace(returncode=0)))
    monkeypatch.setattr(rt, "backup", Mock(return_value=directory))
    monkeypatch.setattr(rt, "initialize", Mock(side_effect=RuntimeError("injected failure")))
    compose = Mock(); monkeypatch.setattr(rt, "compose", compose)
    with pytest.raises(RuntimeError, match="injected failure"):
        rt.migrate_native({}, args())
    assert rt.read_state()["mode"] == "legacy"
    assert all("--volumes" not in call.args and "down" not in call.args for call in compose.call_args_list)
    assert compose.call_args.kwargs["native"] is False
    assert compose.call_args.args[1:4] == ("up", "-d", "--no-build")


def test_production_ui_does_not_import_fixture_auth():
    root = Path(__file__).parents[2] / "modern-ui"
    main = (root / "src/main.tsx").read_text()
    assert "native/native.css" in main
    assert "AuthFixture" not in main
    assert "legacyUrl" not in (root / "src/App.tsx").read_text()
    assert "iframe" not in (root / "src/App.tsx").read_text().lower()

def test_successful_rollback_never_deletes_native_or_legacy_data(rt, monkeypatch):
    backup = rt.RUNTIME / "backups/cutover"; backup.mkdir(parents=True)
    (backup / "manifest.json").write_text('{"source":"legacy"}')
    (backup / "rollback-images.json").write_text('{"services":{}}')
    (backup / "docker-compose.yml").write_text('services: {}\n')
    (backup / ".env").write_text('A=B\n')
    (backup / "docker-compose.modern-ui-override.yml").write_text('services: {}\n')
    rt.save_state({"mode":"native","installed":True,"backup":".scenescape-runtime/backups/cutover"})
    compose=Mock(); run=Mock(return_value=SimpleNamespace(returncode=0)); monkeypatch.setattr(rt,"compose",compose); monkeypatch.setattr(rt,"run",run)
    config={"COMPOSE_PROJECT_NAME":"test","SCENESCAPE_PROFILE":"default"}
    rt.rollback(config,args())
    assert rt.read_state()["mode"]=="legacy"
    assert all("--volumes" not in call.args for call in compose.call_args_list)
    command=run.call_args.args[0]
    assert "down" not in command and "--no-build" in command


def test_identity_reconcile_command_verifies_audience_mapper(rt, monkeypatch):
    rt.save_state({"mode": "native", "installed": True})
    monkeypatch.setattr(rt, "doctor", Mock())
    compose = Mock(); monkeypatch.setattr(rt, "compose", compose)
    reconcile = Mock(); monkeypatch.setattr(rt, "reconcile_identity", reconcile)
    rt.reconcile_identity_command({"COMPOSE_PROJECT_NAME": "test"})
    assert compose.call_args.args[1:4] == ("up", "-d", "keycloak")
    reconcile.assert_called_once()

def test_reconcile_identity_contains_readback_verification():
    source = (Path(__file__).parents[2] / "tools/native_runtime.py").read_text()
    assert "Keycloak did not persist the scenescape-api audience mapper." in source
    assert "included.custom.audience" in source
    assert "reconcile-identity" in source
