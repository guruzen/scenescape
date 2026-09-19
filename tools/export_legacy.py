"""One-shot export INSIDE the old manager image, while its server is stopped.

This file is migration tooling only. Neither the native API nor its worker
imports Django. stdout is a private migration snapshot; diagnostics use stderr.
"""
import contextlib
import json
import os
import sys
from datetime import datetime, timezone

os.environ["DJANGO_SETTINGS_MODULE"] = "sscape.settings"
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
