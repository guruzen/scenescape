#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SceneScape 2026.2.0 modern UI + Keycloak lifecycle helper for WSL2/Linux.

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${ROOT_DIR}/.scenescape-modern.env"
RUNTIME_DIR="${ROOT_DIR}/.scenescape-runtime"
RUNTIME_REALM_FILE="${RUNTIME_DIR}/scenescape-realm.json"
SOURCE_REALM_FILE="${ROOT_DIR}/modern-ui/keycloak/scenescape-realm.json"
BASE_COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"
MODERN_COMPOSE_FILE="${ROOT_DIR}/sample_data/docker-compose.modern-ui-override.yml"
BASE_ENV_FILE="${ROOT_DIR}/.env"
VERSION_FILE="${ROOT_DIR}/version.txt"
DEFAULT_PUBLIC_URL="http://localhost:8088"
DEFAULT_MODERN_UI_PORT="8088"
DEFAULT_PROFILE="controller"

log() {
  printf '\n==> %s\n' "$*"
}

info() {
  printf '    %s\n' "$*"
}

warn() {
  printf 'WARNING: %s\n' "$*" >&2
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF_USAGE'
SceneScape modern UI + Keycloak lifecycle helper

Usage:
  ./scenescape.sh <command> [options]

Commands:
  configure   Create/update local configuration and Keycloak realm.
  build       Build SceneScape core images and the modern React UI image.
  install     One-command fresh install: configure, build, initialize, start.
  start       Start/reconcile the configured stack without rebuilding images.
  stop        Stop containers while preserving data and configuration.
  restart     Stop and start the stack.
  status      Show container status and endpoint information.
  logs        Follow logs. Optionally pass service names after "logs".
  open        Open the modern UI in the Windows/default browser when possible.
  uninstall   Remove the installation and persistent data after confirmation.
  help        Show this help.

Configure options:
  --public-url URL       Browser-visible base URL (default: http://localhost:8088)
  --port PORT            Host port for the modern UI (default: 8088)
  --admin-user USER      Keycloak bootstrap admin username (default: admin)
  --regenerate-secrets   Generate new Django and Keycloak passwords.

Uninstall options:
  --yes                   Skip the destructive confirmation prompt.

Typical WSL2 flow:
  ./scenescape.sh install
  ./scenescape.sh status
  ./scenescape.sh open
  ./scenescape.sh stop
  ./scenescape.sh start
  ./scenescape.sh uninstall

Local secrets are stored in .scenescape-modern.env with mode 600 and are ignored
by Git. Do not commit or share that file.
EOF_USAGE
}

is_wsl() {
  grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null
}

check_wsl_layout() {
  if is_wsl; then
    info "WSL2 detected."
    case "${ROOT_DIR}" in
      /mnt/*)
        warn "Repository is under ${ROOT_DIR}. For faster Docker/build I/O, prefer the WSL Linux filesystem (for example ~/src/scenescape)."
        ;;
    esac
  else
    warn "WSL2 was not detected. The script also works on Linux, but this branch is optimized/documented for WSL2 usage."
  fi
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command '$1' was not found."
}

check_common_tools() {
  require_command make
  require_command openssl
  require_command python3
  require_command docker
}

check_docker() {
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required (the 'docker compose' command)."
  if ! docker info >/dev/null 2>&1; then
    if is_wsl; then
      die "Docker is installed but the daemon is not reachable. Start Docker Desktop in Windows and enable Settings > Resources > WSL Integration for this distribution."
    fi
    die "Docker is installed but the daemon is not reachable."
  fi
}

preflight() {
  check_wsl_layout
  check_common_tools
  check_docker
}

random_secret() {
  openssl rand -hex 24
}

validate_public_url() {
  local value="$1"
  [[ "${value}" =~ ^https?://[^[:space:]]+$ ]] || die "Public URL must start with http:// or https:// and contain no spaces: ${value}"
  [[ "${value}" != */ ]] || die "Public URL must not end with '/': ${value}"
}

validate_port() {
  local value="$1"
  [[ "${value}" =~ ^[0-9]+$ ]] || die "Port must be numeric: ${value}"
  (( value >= 1 && value <= 65535 )) || die "Port must be between 1 and 65535: ${value}"
}

load_config_if_present() {
  if [[ -f "${CONFIG_FILE}" ]]; then
    # shellcheck disable=SC1090
    set -a
    source "${CONFIG_FILE}"
    set +a
  fi
}

load_config() {
  [[ -f "${CONFIG_FILE}" ]] || die "Configuration is missing. Run './scenescape.sh configure' or './scenescape.sh install'."
  load_config_if_present

  : "${SUPASS:?SUPASS is missing from ${CONFIG_FILE}}"
  : "${KEYCLOAK_ADMIN_USERNAME:?KEYCLOAK_ADMIN_USERNAME is missing from ${CONFIG_FILE}}"
  : "${KEYCLOAK_ADMIN_PASSWORD:?KEYCLOAK_ADMIN_PASSWORD is missing from ${CONFIG_FILE}}"
  : "${SCENESCAPE_PUBLIC_URL:?SCENESCAPE_PUBLIC_URL is missing from ${CONFIG_FILE}}"
  : "${MODERN_UI_PORT:?MODERN_UI_PORT is missing from ${CONFIG_FILE}}"
  : "${SCENESCAPE_PROFILE:?SCENESCAPE_PROFILE is missing from ${CONFIG_FILE}}"
  : "${SCENESCAPE_KEYCLOAK_REALM_FILE:?SCENESCAPE_KEYCLOAK_REALM_FILE is missing from ${CONFIG_FILE}}"

  export SUPASS KEYCLOAK_ADMIN_USERNAME KEYCLOAK_ADMIN_PASSWORD
  export SCENESCAPE_PUBLIC_URL MODERN_UI_PORT SCENESCAPE_PROFILE
  export SCENESCAPE_KEYCLOAK_REALM_FILE COMPOSE_PROJECT_NAME
}

generate_runtime_realm() {
  local public_url="$1"
  mkdir -p "${RUNTIME_DIR}"
  chmod 700 "${RUNTIME_DIR}"
  [[ -f "${SOURCE_REALM_FILE}" ]] || die "Keycloak realm template not found: ${SOURCE_REALM_FILE}"

  python3 - "${SOURCE_REALM_FILE}" "${RUNTIME_REALM_FILE}" "${public_url}" <<'PY'
import json
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
public_url = sys.argv[3].rstrip("/")

realm = json.loads(source.read_text(encoding="utf-8"))
clients = realm.get("clients", [])
client = next((item for item in clients if item.get("clientId") == "scenescape-ui"), None)
if client is None:
    raise SystemExit("scenescape-ui client not found in realm template")

client["redirectUris"] = [f"{public_url}/*"]
client["webOrigins"] = [public_url]
attributes = client.setdefault("attributes", {})
attributes["pkce.code.challenge.method"] = "S256"
attributes["post.logout.redirect.uris"] = f"{public_url}/*"

destination.write_text(json.dumps(realm, indent=2) + "\n", encoding="utf-8")
PY
  chmod 600 "${RUNTIME_REALM_FILE}"
}

write_config() {
  local public_url="$1"
  local port="$2"
  local admin_user="$3"
  local supass="$4"
  local keycloak_password="$5"

  umask 077
  {
    printf '# Generated by ./scenescape.sh configure. Do not commit this file.\n'
    printf 'SUPASS=%q\n' "${supass}"
    printf 'KEYCLOAK_ADMIN_USERNAME=%q\n' "${admin_user}"
    printf 'KEYCLOAK_ADMIN_PASSWORD=%q\n' "${keycloak_password}"
    printf 'SCENESCAPE_PUBLIC_URL=%q\n' "${public_url}"
    printf 'MODERN_UI_PORT=%q\n' "${port}"
    printf 'SCENESCAPE_PROFILE=%q\n' "${DEFAULT_PROFILE}"
    printf 'SCENESCAPE_KEYCLOAK_REALM_FILE=%q\n' './.scenescape-runtime/scenescape-realm.json'
    printf 'COMPOSE_PROJECT_NAME=%q\n' 'scenescape'
  } > "${CONFIG_FILE}"
  chmod 600 "${CONFIG_FILE}"
}

cmd_configure() {
  check_wsl_layout
  require_command openssl
  require_command python3

  local existing_supass=""
  local existing_keycloak_password=""
  local public_url="${DEFAULT_PUBLIC_URL}"
  local port="${DEFAULT_MODERN_UI_PORT}"
  local admin_user="admin"
  local regenerate="false"
  local public_url_explicit="false"

  if [[ -f "${CONFIG_FILE}" ]]; then
    load_config_if_present
    existing_supass="${SUPASS:-}"
    existing_keycloak_password="${KEYCLOAK_ADMIN_PASSWORD:-}"
    public_url="${SCENESCAPE_PUBLIC_URL:-${public_url}}"
    port="${MODERN_UI_PORT:-${port}}"
    admin_user="${KEYCLOAK_ADMIN_USERNAME:-${admin_user}}"
  fi

  while (($#)); do
    case "$1" in
      --public-url)
        (($# >= 2)) || die "--public-url requires a value"
        public_url="$2"
        public_url_explicit="true"
        shift 2
        ;;
      --port)
        (($# >= 2)) || die "--port requires a value"
        port="$2"
        shift 2
        ;;
      --admin-user)
        (($# >= 2)) || die "--admin-user requires a value"
        admin_user="$2"
        shift 2
        ;;
      --regenerate-secrets)
        regenerate="true"
        shift
        ;;
      -h|--help)
        usage
        return 0
        ;;
      *)
        die "Unknown configure option: $1"
        ;;
    esac
  done

  if [[ "${public_url_explicit}" == "false" && "${public_url}" =~ ^http://localhost:[0-9]+$ ]]; then
    public_url="http://localhost:${port}"
  fi

  validate_public_url "${public_url}"
  validate_port "${port}"
  [[ -n "${admin_user}" ]] || die "Keycloak admin username cannot be empty."

  local supass="${existing_supass}"
  local keycloak_password="${existing_keycloak_password}"
  if [[ "${regenerate}" == "true" || -z "${supass}" ]]; then
    supass="$(random_secret)"
  fi
  if [[ "${regenerate}" == "true" || -z "${keycloak_password}" ]]; then
    keycloak_password="$(random_secret)"
  fi

  generate_runtime_realm "${public_url}"
  write_config "${public_url}" "${port}" "${admin_user}" "${supass}" "${keycloak_password}"

  log "Configuration written"
  info "Config: ${CONFIG_FILE}"
  info "Runtime Keycloak realm: ${RUNTIME_REALM_FILE}"
  info "Public URL: ${public_url}"
  info "Modern UI port: ${port}"
  info "Keycloak bootstrap admin: ${admin_user}"
  info "Secrets were preserved if configuration already existed. Use --regenerate-secrets to replace them."
  if command -v docker >/dev/null 2>&1 && docker volume inspect scenescape_vol-keycloak >/dev/null 2>&1; then
    warn "A persistent Keycloak volume already exists. Realm import only applies on first creation. URL/client changes may require Keycloak admin updates or a full uninstall/reinstall."
  fi
}

ensure_config() {
  if [[ ! -f "${CONFIG_FILE}" ]]; then
    log "No local configuration found; creating WSL2 defaults"
    cmd_configure
  fi
  load_config
}

version() {
  [[ -f "${VERSION_FILE}" ]] || die "version.txt not found. Run this script from a SceneScape source checkout."
  tr -d '[:space:]' < "${VERSION_FILE}"
}

ensure_base_runtime_files() {
  [[ -d "${ROOT_DIR}/manager/secrets" ]] || die "SceneScape secrets are missing. Run './scenescape.sh build' or './scenescape.sh install' first."
  make docker-compose.yml .env
}

compose() {
  local args=(
    docker compose
    --env-file "${BASE_ENV_FILE}"
    -f "${BASE_COMPOSE_FILE}"
    -f "${MODERN_COMPOSE_FILE}"
    --profile "${SCENESCAPE_PROFILE:-${DEFAULT_PROFILE}}"
  )
  "${args[@]}" "$@"
}

cmd_build() {
  preflight
  ensure_config
  cd "${ROOT_DIR}"

  log "Building SceneScape core images and installing models"
  make build-core

  log "Building modern React UI image"
  docker build -t "intel/scenescape-modern-ui:$(version)" modern-ui

  log "Generating Docker Compose runtime files"
  make docker-compose.yml .env

  log "Validating merged Compose configuration"
  compose config --quiet

  log "Build complete"
}

sample_data_volume_exists() {
  docker volume inspect "${COMPOSE_PROJECT_NAME:-scenescape}_vol-sample-data" >/dev/null 2>&1
}

initialize_sample_data_if_needed() {
  if sample_data_volume_exists; then
    info "Sample-data volume already exists; preserving it."
  else
    log "Initializing SceneScape sample data"
    make init-sample-data
  fi
}

wait_for_endpoint() {
  local name="$1"
  local url="$2"
  local attempts="${3:-90}"
  local delay="${4:-2}"
  local i

  if ! command -v curl >/dev/null 2>&1; then
    warn "curl is not installed; skipping HTTP readiness check for ${name}."
    return 0
  fi

  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS --max-time 3 "${url}" >/dev/null 2>&1; then
      info "${name} is ready: ${url}"
      return 0
    fi
    sleep "${delay}"
  done

  warn "${name} did not become ready at ${url}. Run './scenescape.sh status' and './scenescape.sh logs'."
  return 1
}

repair_keycloak_client_scopes() {
  local kcadm="/opt/keycloak/bin/kcadm.sh"
  local client_id scope_id current_scopes

  log "Checking Keycloak client scopes"

  if ! compose exec -T keycloak "${kcadm}" config credentials \
      --server http://127.0.0.1:8080/auth \
      --realm master \
      --user "${KEYCLOAK_ADMIN_USERNAME}" \
      --password "${KEYCLOAK_ADMIN_PASSWORD}" >/dev/null 2>&1; then
    warn "Could not authenticate the Keycloak admin CLI; verify KEYCLOAK_ADMIN_USERNAME/PASSWORD in .scenescape-modern.env."
    return 1
  fi

  client_id="$(compose exec -T keycloak "${kcadm}" get clients -r scenescape \
      -q clientId=scenescape-ui --fields id --format csv --noquotes 2>/dev/null | awk 'NR==2 {print $1}')"
  [[ -n "${client_id}" ]] || { warn "Keycloak client 'scenescape-ui' was not found."; return 1; }

  scope_id="$(compose exec -T keycloak "${kcadm}" get client-scopes -r scenescape \
      --fields id,name --format csv --noquotes 2>/dev/null | awk -F, '$2=="basic" {print $1; exit}')"
  [[ -n "${scope_id}" ]] || { warn "Keycloak client scope 'basic' was not found."; return 1; }

  current_scopes="$(compose exec -T keycloak "${kcadm}" get "clients/${client_id}/default-client-scopes" -r scenescape \
      --fields name --format csv --noquotes 2>/dev/null || true)"
  if printf '%s\n' "${current_scopes}" | grep -qx 'basic'; then
    info "Keycloak client scope 'basic' is already attached."
    return 0
  fi

  if compose exec -T keycloak "${kcadm}" update \
      "clients/${client_id}/default-client-scopes/${scope_id}" -r scenescape >/dev/null 2>&1; then
    info "Attached Keycloak default client scope 'basic' (provides access-token sub/auth_time claims)."
    return 0
  fi

  warn "Could not attach Keycloak client scope 'basic' automatically. Use the Keycloak admin console: Clients > scenescape-ui > Client scopes > Add client scope > basic > Default."
  return 1
}

print_endpoints() {
  info "Modern UI: ${SCENESCAPE_PUBLIC_URL}"
  info "Keycloak admin: ${SCENESCAPE_PUBLIC_URL}/auth/admin/"
  info "Django fallback: ${SCENESCAPE_PUBLIC_URL}/legacy/"
  info "Original Django endpoint: https://localhost"
}

cmd_start() {
  preflight
  ensure_config
  cd "${ROOT_DIR}"
  ensure_base_runtime_files
  initialize_sample_data_if_needed

  log "Starting SceneScape, Keycloak and the modern UI"
  compose up -d --no-build

  log "Waiting for browser endpoints"
  local local_base="http://127.0.0.1:${MODERN_UI_PORT}"
  wait_for_endpoint "Modern UI" "${local_base}/healthz" 90 2 || true
  if wait_for_endpoint "Keycloak realm" "${local_base}/auth/realms/scenescape/.well-known/openid-configuration" 90 2; then
    repair_keycloak_client_scopes || true
  fi

  log "SceneScape is started"
  print_endpoints
  info "First login: open the Keycloak admin console, create a user in realm 'scenescape', and assign scenescape-viewer or scenescape-admin."
}

cmd_install() {
  preflight
  if [[ ! -f "${CONFIG_FILE}" ]]; then
    cmd_configure
  else
    load_config
    generate_runtime_realm "${SCENESCAPE_PUBLIC_URL}"
  fi

  cmd_build
  cmd_start

  log "Installation complete"
  print_endpoints
  info "Use './scenescape.sh stop' to stop without losing data."
}

cmd_stop() {
  preflight
  ensure_config
  cd "${ROOT_DIR}"
  if [[ ! -f "${BASE_COMPOSE_FILE}" || ! -f "${BASE_ENV_FILE}" ]]; then
    info "Generated Compose files are absent; nothing to stop."
    return 0
  fi

  log "Stopping SceneScape containers (data is preserved)"
  compose stop
  log "Stopped"
}

cmd_restart() {
  cmd_stop
  cmd_start
}

cmd_status() {
  preflight
  ensure_config
  cd "${ROOT_DIR}"
  if [[ ! -f "${BASE_COMPOSE_FILE}" || ! -f "${BASE_ENV_FILE}" ]]; then
    info "Generated Compose files do not exist. Run './scenescape.sh install'."
    return 0
  fi

  compose ps
  printf '\n'
  print_endpoints
}

cmd_logs() {
  preflight
  ensure_config
  cd "${ROOT_DIR}"
  [[ -f "${BASE_COMPOSE_FILE}" && -f "${BASE_ENV_FILE}" ]] || die "Runtime Compose files are missing. Run './scenescape.sh install'."
  compose logs -f --tail 200 "$@"
}

cmd_open() {
  ensure_config
  if command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "${SCENESCAPE_PUBLIC_URL}" >/dev/null 2>&1 || true
  elif command -v wslview >/dev/null 2>&1; then
    wslview "${SCENESCAPE_PUBLIC_URL}"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${SCENESCAPE_PUBLIC_URL}" >/dev/null 2>&1 &
  else
    info "Open ${SCENESCAPE_PUBLIC_URL} in your browser."
  fi
}

confirm_uninstall() {
  local assume_yes="$1"
  if [[ "${assume_yes}" == "true" ]]; then
    return 0
  fi

  cat <<'EOF_WARNING'

UNINSTALL IS DESTRUCTIVE.
It removes SceneScape containers and persistent volumes, including:
  - PostgreSQL SceneScape data
  - Keycloak users and role assignments
  - media, sample-data, migrations and model volumes
  - generated SceneScape secrets and runtime configuration
  - locally built core/modern UI images where the existing Makefiles clean them

The Git checkout itself is not deleted.
EOF_WARNING
  printf 'Type UNINSTALL to continue: '
  local answer
  read -r answer
  [[ "${answer}" == "UNINSTALL" ]] || die "Uninstall cancelled."
}

cmd_uninstall() {
  preflight
  local assume_yes="false"
  while (($#)); do
    case "$1" in
      --yes)
        assume_yes="true"
        shift
        ;;
      -h|--help)
        usage
        return 0
        ;;
      *)
        die "Unknown uninstall option: $1"
        ;;
    esac
  done

  confirm_uninstall "${assume_yes}"
  load_config_if_present
  export SCENESCAPE_PROFILE="${SCENESCAPE_PROFILE:-${DEFAULT_PROFILE}}"
  export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-scenescape}"
  export KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-unused-for-teardown}"
  export SUPASS="${SUPASS:-unused-for-teardown}"
  cd "${ROOT_DIR}"

  if [[ -f "${BASE_COMPOSE_FILE}" && -f "${BASE_ENV_FILE}" ]]; then
    log "Removing containers, networks and persistent volumes"
    compose down -v --remove-orphans || warn "Compose teardown returned an error; continuing cleanup."
  fi

  log "Cleaning SceneScape generated artifacts and core images"
  make clean-core || warn "SceneScape make clean-core reported an error; continuing local cleanup."

  local image_version
  image_version="$(version)"
  docker image rm -f "intel/scenescape-modern-ui:${image_version}" >/dev/null 2>&1 || true
  docker image rm -f "intel/scenescape-modern-ui:latest" >/dev/null 2>&1 || true

  rm -rf "${RUNTIME_DIR}"
  rm -f "${CONFIG_FILE}" "${BASE_COMPOSE_FILE}" "${BASE_ENV_FILE}" "${ROOT_DIR}/.scenescape-profile"

  log "Uninstall complete"
  info "The Git checkout remains at ${ROOT_DIR}."
}

main() {
  cd "${ROOT_DIR}"
  local command="${1:-help}"
  if (($#)); then
    shift
  fi

  case "${command}" in
    configure)
      cmd_configure "$@"
      ;;
    build)
      cmd_build "$@"
      ;;
    install)
      cmd_install "$@"
      ;;
    start)
      cmd_start "$@"
      ;;
    stop)
      cmd_stop "$@"
      ;;
    restart)
      cmd_restart "$@"
      ;;
    status)
      cmd_status "$@"
      ;;
    logs)
      cmd_logs "$@"
      ;;
    open)
      cmd_open "$@"
      ;;
    uninstall)
      cmd_uninstall "$@"
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      usage >&2
      die "Unknown command: ${command}"
      ;;
  esac
}

main "$@"
