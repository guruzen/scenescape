#!/usr/bin/env python3
"""Non-destructive native data seed/recovery helpers.

This module reuses the lifecycle helper's Compose configuration. It never drops
volumes or deletes legacy/native rows. Legacy recovery launches the Django
manager only as a one-shot serializer against the existing PostgreSQL tables.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import native_runtime as rt


def _require_native():
    state = rt.read_state()
    if state.get("mode") != "native" or not state.get("installed"):
        rt.fail("This command requires an installed native runtime.")
    return state


def seed_native(config):
    _require_native()
    rt.log("Importing upstream sample SceneScape data into native tables without deleting existing rows")
    rt.run(["make", "init-sample-data"], env=rt.environment(config))
    rt.compose(config, "run", "--rm", "-T", "--no-deps", "web", "seed", "/data/samples/Retail.json", native=True)
    print("Native sample data imported/upserted. Existing native and legacy rows were preserved.")


def recover_legacy(config):
    state = _require_native()
    rt.doctor()
    directory = rt.RUNTIME / "backups" / ("recover-legacy-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(parents=True, mode=0o700)
    rt.log("Recovering legacy SceneScape configuration into native tables; no legacy/native rows are deleted")

    rendered = json.loads(rt.compose(config, "config", "--format", "json", native=False, capture=True).stdout)
    legacy_image = rendered.get("services", {}).get("web", {}).get("image")
    if not legacy_image:
        rt.fail("The legacy Compose definition does not identify a manager image.")
    if rt.run(["docker", "image", "inspect", legacy_image], capture=True, check=False).returncode:
        rt.log("Legacy manager image is not local; building it only for read-only export")
        rt.run(["make", "manager"], env=rt.environment(config))
        if rt.run(["docker", "image", "inspect", legacy_image], capture=True, check=False).returncode:
            rt.fail("Legacy manager image is unavailable after build; native data was not changed.")

    snapshot_path = directory / "legacy-snapshot.json"
    with snapshot_path.open("wb") as file:
        rt.compose(
            config, "run", "--rm", "-T", "--no-deps", "--entrypoint", "python3", "web", "-",
            native=False, data=(rt.ROOT / "tools/export_legacy.py").read_bytes(), output=file,
        )
    payload = json.loads(snapshot_path.read_text())
    if not isinstance(payload.get("scenes"), list) or "_migration" not in payload:
        rt.fail("Legacy export did not produce a complete snapshot; native data was not changed.")
    snapshot_path.chmod(0o600)
    rt.private_write(directory / "manifest.json", json.dumps({
        "source": "legacy-recovery",
        "counts": payload["_migration"].get("counts", {}),
        "legacy_image": legacy_image,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }, indent=2))

    rt.compose(
        config, "run", "--rm", "-T", "--no-deps", "--entrypoint", "python", "web",
        "-m", "scenescape_api.migrate_legacy", native=True, data=snapshot_path.read_bytes(),
    )
    state["legacy_recovered_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    state["legacy_recovery_snapshot"] = str(snapshot_path.relative_to(rt.ROOT))
    rt.save_state(state)
    print(f"Legacy configuration recovered into native tables. Snapshot retained at {snapshot_path}. No volumes or old tables were deleted.")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"recover-legacy-data", "seed-native-data"}:
        raise SystemExit("usage: native_data.py recover-legacy-data|seed-native-data")
    config = rt.load_config()
    if sys.argv[1] == "recover-legacy-data":
        recover_legacy(config)
    else:
        seed_native(config)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
