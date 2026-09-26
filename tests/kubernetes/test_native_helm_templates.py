# SPDX-License-Identifier: Apache-2.0
"""Render-level parity checks for the reversible native Helm deployment."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "kubernetes" / "scenescape-chart"


def _helm_template(*extra: str) -> list[dict]:
  if shutil.which("helm") is None:
    pytest.skip("helm is required for chart render tests")
  cmd = [
    "helm", "template", "scenescape", str(CHART),
    "--namespace", "scenescape",
    "--set", "supass=test-password",
    "--set", "pgserver.password=test-password",
    "--set", "certdomain=scenescape.example.test",
    *extra,
  ]
  result = subprocess.run(cmd, capture_output=True, text=True, check=False)
  assert result.returncode == 0, result.stderr
  return [doc for doc in yaml.safe_load_all(result.stdout) if isinstance(doc, dict)]


def _resource(docs, kind: str, name: str) -> dict:
  for doc in docs:
    if doc.get("kind") == kind and doc.get("metadata", {}).get("name") == name:
      return doc
  raise AssertionError(f"{kind}/{name} was not rendered")


def test_native_mode_replaces_django_without_renaming_stateful_interfaces():
  docs = _helm_template(
    "--set", "native.enabled=true",
    "--set", "native.migrateLegacy=true",
    "--set", "keycloak.enabled=true",
  )

  web = _resource(docs, "Deployment", "scenescape-web-dep")
  container = web["spec"]["template"]["spec"]["containers"][0]
  assert container["image"].startswith("intel/scenescape-control-api:")
  assert container["args"] == ["serve"]
  assert web["spec"]["selector"]["matchLabels"]["app"] == "scenescape-web"

  service = _resource(docs, "Service", "web")
  assert service["spec"]["selector"]["app"] == "scenescape-web"
  assert any(port["port"] == 443 for port in service["spec"]["ports"])

  _resource(docs, "PersistentVolumeClaim", "scenescape-media-pvc")
  _resource(docs, "StatefulSet", "scenescape-pgserver")
  _resource(docs, "Deployment", "scenescape-native-worker")
  _resource(docs, "Deployment", "scenescape-modern-ui")
  _resource(docs, "Deployment", "scenescape-keycloak")
  _resource(docs, "Job", "scenescape-native-export-legacy")
  _resource(docs, "Job", "scenescape-keycloak-reconcile")


def test_legacy_render_remains_available_for_helm_rollback():
  docs = _helm_template("--set", "native.enabled=false")
  web = _resource(docs, "Deployment", "scenescape-web-dep")
  container = web["spec"]["template"]["spec"]["containers"][0]
  assert "scenescape-manager:" in container["image"]
  assert not any(
    doc.get("kind") == "Deployment"
    and doc.get("metadata", {}).get("name") == "scenescape-native-worker"
    for doc in docs
  )

  service = _resource(docs, "Service", "web")
  assert service["spec"]["selector"]["app"] == "scenescape-web"
  _resource(docs, "PersistentVolumeClaim", "scenescape-media-pvc")
  _resource(docs, "StatefulSet", "scenescape-pgserver")


def test_embedded_keycloak_state_is_retained():
  docs = _helm_template(
    "--set", "native.enabled=true",
    "--set", "keycloak.enabled=true",
  )
  pvc = _resource(docs, "PersistentVolumeClaim", "scenescape-keycloak-data")
  assert pvc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"

  deployment = _resource(docs, "Deployment", "scenescape-keycloak")
  mounts = deployment["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]
  assert any(item["mountPath"] == "/opt/keycloak/data/h2" for item in mounts)


def test_native_cutover_has_schema_and_single_import_guards():
  docs = _helm_template(
    "--set", "native.enabled=true",
    "--set", "native.migrateLegacy=true",
    "--set", "keycloak.enabled=true",
  )
  web = _resource(docs, "Deployment", "scenescape-web-dep")
  init = {item["name"]: item for item in web["spec"]["template"]["spec"]["initContainers"]}
  assert "native-schema" in init
  assert "import-legacy-snapshot" in init
  script = "\n".join(init["import-legacy-snapshot"].get("args", []))
  assert "native-import-complete" in script
  assert "scenescape_api.migrate_legacy" in script


def test_native_api_wires_processing_services():
  docs = _helm_template(
    "--set", "native.enabled=true",
    "--set", "keycloak.enabled=true",
    "--set", "mapping.enabled=true",
  )
  web = _resource(docs, "Deployment", "scenescape-web-dep")
  env = {
    item["name"]: item.get("value")
    for item in web["spec"]["template"]["spec"]["containers"][0]["env"]
    if "name" in item
  }
  assert env["MQTT_HOST"] == "broker.scenescape.svc.cluster.local"
  assert env["AUTOCALIBRATION_URL"] == "https://autocalibration.scenescape.svc.cluster.local:8443"
  assert env["MAPPING_SERVICE_URL"] == "https://mapping.scenescape.svc.cluster.local:8444/v1"
  assert env["OIDC_AUDIENCE"] == "scenescape-api"
