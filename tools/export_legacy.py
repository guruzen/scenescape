"""One-shot export INSIDE the old manager image, while its server is stopped.

This file is migration tooling only. Neither the native API nor its worker
imports Django. stdout is a private migration snapshot; diagnostics use stderr.
"""
import contextlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# The normal legacy container entrypoint establishes the application cwd/PYTHONPATH
# and materializes manager.secrets before launching Django. Recovery deliberately
# bypasses that entrypoint, so reproduce only those import prerequisites here.
project_root = Path(os.environ.get("SCENESCAPE_HOME", "/home/scenescape/Scenescape"))
if not (project_root / "manager" / "settings.py").is_file():
    raise RuntimeError(f"Legacy manager sources are missing under {project_root}")
sys.path.insert(0, str(project_root))
os.chdir(project_root)

import manager  # noqa: E402

if importlib.util.find_spec("manager.secrets") is None:
    secret_path = Path(os.environ.get("SCENESCAPE_DJANGO_SECRETS", "/run/secrets/django/secrets.py"))
    if not secret_path.is_file():
        raise RuntimeError(f"Legacy Django secrets are not mounted at {secret_path}")
    spec = importlib.util.spec_from_file_location("manager.secrets", secret_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load legacy Django secrets from {secret_path}")
    secrets_module = importlib.util.module_from_spec(spec)
    sys.modules["manager.secrets"] = secrets_module
    setattr(manager, "secrets", secrets_module)
    spec.loader.exec_module(secrets_module)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "manager.settings")
os.environ.pop("BROKER", None)
sys.argv = ["migration-export", "--dbtype", "postgres"]

with contextlib.redirect_stdout(sys.stderr):
    import django
    django.setup()
    from django.db import transaction
    from manager import models, serializers

    resources = {
        "scenes": (models.Scene, serializers.SceneSerializer),
        "cameras": (models.Cam, serializers.CamSerializer),
        "sensors": (models.SingletonSensor, serializers.SingletonSerializer),
        "regions": (models.Region, serializers.RegionSerializer),
        "tripwires": (models.Tripwire, serializers.TripwireSerializer),
        "assets": (models.Asset3D, serializers.Asset3DSerializer),
        "children": (models.ChildScene, serializers.ChildSceneSerializer),
        "calibrationmarkers": (models.CalibrationMarker, serializers.CalibrationMarkerSerializer),
    }
    with transaction.atomic():
        # All old services have been stopped before this one-shot export.
        payload = {name: list(serializer(model.objects.all(), many=True).data)
                   for name, (model, serializer) in resources.items()}
        payload["_migration"] = {
            "format": "scenescape-2026.2-export/1",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "counts": {name: len(payload[name]) for name in resources},
        }
print(json.dumps(payload, default=str, allow_nan=False))
