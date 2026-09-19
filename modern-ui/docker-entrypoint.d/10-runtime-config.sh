#!/bin/sh
set -eu
escape_js(){ printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
cat > /usr/share/nginx/html/config.js <<EOF_CONFIG
window.__SCENESCAPE_CONFIG__ = {
  apiBaseUrl: "$(escape_js "${SCENESCAPE_API_BASE_URL:-}")",
  keycloakUrl: "$(escape_js "${SCENESCAPE_KEYCLOAK_URL:-/auth}")",
  keycloakRealm: "$(escape_js "${SCENESCAPE_KEYCLOAK_REALM:-scenescape}")",
  keycloakClientId: "$(escape_js "${SCENESCAPE_KEYCLOAK_CLIENT_ID:-scenescape-ui}")",
  appTitle: "$(escape_js "${SCENESCAPE_APP_TITLE:-SceneScape}")"
};
EOF_CONFIG
