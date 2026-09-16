#!/bin/sh
set -eu

escape_js() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

API_BASE="$(escape_js "${SCENESCAPE_API_BASE_URL:-}")"
KC_URL="$(escape_js "${SCENESCAPE_KEYCLOAK_URL:-/auth}")"
KC_REALM="$(escape_js "${SCENESCAPE_KEYCLOAK_REALM:-scenescape}")"
KC_CLIENT="$(escape_js "${SCENESCAPE_KEYCLOAK_CLIENT_ID:-scenescape-ui}")"
LEGACY="$(escape_js "${SCENESCAPE_LEGACY_BASE_URL:-/legacy/}")"
TITLE="$(escape_js "${SCENESCAPE_APP_TITLE:-SceneScape}")"

cat > /usr/share/nginx/html/config.js <<EOF_CONFIG
window.__SCENESCAPE_CONFIG__ = {
  apiBaseUrl: "${API_BASE}",
  keycloakUrl: "${KC_URL}",
  keycloakRealm: "${KC_REALM}",
  keycloakClientId: "${KC_CLIENT}",
  legacyBaseUrl: "${LEGACY}",
  appTitle: "${TITLE}"
};
EOF_CONFIG
