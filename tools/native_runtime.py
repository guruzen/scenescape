#!/usr/bin/env python3
"""WSL2 lifecycle, migration and rollback. Uses only Python's standard library.

No system-wide cleanup, implicit volume deletion, credential rotation, database
reset, or automatic cutover of an existing legacy installation is performed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".scenescape-runtime"
STATE = RUNTIME / "native-state.json"
CONFIG = ROOT / ".scenescape-modern.env"
OLD_FILES = ["docker-compose.yml", ".env", "sample_data/docker-compose.modern-ui-override.yml"]
SECRET_KEYS = ("SUPASS", "KEYCLOAK_ADMIN_USERNAME", "KEYCLOAK_ADMIN_PASSWORD", "SCENESCAPE_API_SIGNING_KEY")
CONFIG_KEYS = (*SECRET_KEYS, "SCENESCAPE_PUBLIC_URL", "MODERN_UI_PORT", "SCENESCAPE_PROFILE", "COMPOSE_PROJECT_NAME", "SCENESCAPE_KEYCLOAK_REALM_FILE")


def fail(message):
    raise RuntimeError(message)


def log(message):
    print(f"\n==> {message}", flush=True)


def run(args, *, env=None, capture=False, data=None, output=None, check=True):
    # Never print arguments: some administrative invocations contain credentials.
    return subprocess.run([str(x) for x in args], cwd=ROOT, env=env,
                          input=data, stdout=output if output else (subprocess.PIPE if capture else None),
                          stderr=subprocess.PIPE if capture else None, check=check)


def private_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + ".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as file:
        file.write(content)
    temp.replace(path)
    path.chmod(0o600)


def read_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save_state(state):
    private_write(STATE, json.dumps(state, indent=2) + "\n")


def load_config(required=True):
    if not CONFIG.exists():
        if required:
            fail("Run ./scenescape.sh configure first.")
        return {}
    # The previous installer wrote Bash %q values, not a generic dotenv file.
    # Read only this user's trusted local file, never a server-supplied script.
    if CONFIG.is_symlink() or CONFIG.stat().st_uid != os.getuid():
        fail("The local configuration must be a regular file owned by your WSL user.")
    result = run(["bash", "-c", 'set -a; source "$1"; env -0', "scenescape-config", CONFIG], capture=True)
    parsed = {}
    for item in result.stdout.split(b"\0"):
        key, _, value = item.partition(b"=")
        if key.decode(errors="ignore") in CONFIG_KEYS:
            parsed[key.decode()] = value.decode()
    return parsed


def base_env():
    result = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.startswith("#"):
                result[key.strip()] = value.strip().strip("\"'")
    return result


def environment(config):
    result = os.environ.copy()
    result.update(base_env())
    result.update(config)
    result["NO_PROXY"] = result.get("NO_PROXY", "") + ",localhost,127.0.0.1,.scenescape.intel.com,pgserver,keycloak"
    result["no_proxy"] = result["NO_PROXY"]
    return result


def compose(config, *args, native=None, capture=False, data=None, output=None, check=True):
    if native is None:
        native = read_state().get("mode") == "native"
    files = [ROOT / "docker-compose.yml", ROOT / "sample_data/docker-compose.modern-ui-override.yml"]
    if native:
        files.append(ROOT / "sample_data/docker-compose.native-override.yml")
    command = ["docker", "compose", "--project-directory", ROOT, "--env-file", ROOT / ".env",
               "-p", config.get("COMPOSE_PROJECT_NAME", "scenescape")]
    for path in files:
        command.extend(["-f", path])
    command.extend(["--profile", config.get("SCENESCAPE_PROFILE", "controller"), *args])
    return run(command, env=environment(config), capture=capture, data=data, output=output, check=check)


def doctor():
    for tool in ("docker", "make", "openssl", "bash"):
        if not shutil.which(tool):
            fail(f"Missing {tool}. Install the WSL2 prerequisites before continuing.")
    result = run(["docker", "info", "--format", "{{.OSType}}"], capture=True, check=False)
    if result.returncode or result.stdout.strip() != b"linux":
        fail("Docker's Linux engine is unavailable. Start Docker Desktop and enable WSL Integration for this distribution.")
    value = run(["docker", "compose", "version", "--short"], capture=True).stdout.decode().strip()
    numbers = tuple(int(x) for x in re.findall(r"\d+", value)[:3])
    if numbers < (2, 24, 4):
        fail("Docker Compose 2.24.4+ is needed for safe service overrides. Update Docker Desktop.")
    if str(ROOT).startswith("/mnt/"):
        print("Warning: prefer ~/src/scenescape on the WSL Linux filesystem for build I/O and file permissions.")
    if os.getuid() == 0:
        fail("Run this script as your normal WSL user, not sudo/root.")
    print(f"Docker Linux engine and Compose {value} are available.")


def origin(value, port):
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        fail("Public URL must be an http(s) origin with no path, credentials, query or trailing slash.")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"):
        fail("Plain HTTP is allowed only on loopback. Use an HTTPS reverse proxy for remote access.")
    if not 1024 <= port <= 65535:
        fail("Choose an unprivileged UI port between 1024 and 65535.")
    if parsed.scheme == "http" and (parsed.port or 80) != port:
        fail("The localhost public URL and --port must match.")
    return value


def configure(args):
    old = load_config(False)
    port = args.port or int(old.get("MODERN_UI_PORT", "8088"))
    public = args.public_url or (f"http://localhost:{port}" if args.port else old.get("SCENESCAPE_PUBLIC_URL", f"http://localhost:{port}"))
    origin(public, port)
    state = read_state()
    if state.get("installed") and old.get("SCENESCAPE_PUBLIC_URL") != public:
        fail("Changing a live issuer requires coordinated Keycloak/client changes. The installer will not silently rewrite it.")
    config = {
        "SUPASS": old.get("SUPASS") or secrets.token_hex(24),
        "KEYCLOAK_ADMIN_USERNAME": args.admin_user or old.get("KEYCLOAK_ADMIN_USERNAME", "admin"),
        "KEYCLOAK_ADMIN_PASSWORD": old.get("KEYCLOAK_ADMIN_PASSWORD") or secrets.token_hex(24),
        "SCENESCAPE_API_SIGNING_KEY": old.get("SCENESCAPE_API_SIGNING_KEY") or secrets.token_hex(32),
        "SCENESCAPE_PUBLIC_URL": public,
        "MODERN_UI_PORT": str(port),
        "SCENESCAPE_PROFILE": old.get("SCENESCAPE_PROFILE", "controller"),
        "COMPOSE_PROJECT_NAME": old.get("COMPOSE_PROJECT_NAME", "scenescape"),
        "SCENESCAPE_KEYCLOAK_REALM_FILE": "./.scenescape-runtime/scenescape-realm.json",
    }
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", config["COMPOSE_PROJECT_NAME"]):
        fail("Invalid Compose project name.")
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,120}", config["KEYCLOAK_ADMIN_USERNAME"]):
        fail("Invalid Keycloak bootstrap username.")
    private_write(CONFIG, "# Private local configuration. Never commit.\n" + "".join(f"{k}={shlex.quote(v)}\n" for k, v in config.items()))
    realm = json.loads((ROOT / "modern-ui/keycloak/scenescape-realm.json").read_text())
    client = next(c for c in realm["clients"] if c["clientId"] == "scenescape-ui")
    client["redirectUris"] = [public + "/*"]
    client["webOrigins"] = [public]
    client["attributes"]["post.logout.redirect.uris"] = public + "/*"
    private_write(RUNTIME / "scenescape-realm.json", json.dumps(realm, indent=2) + "\n")
    # No credentials are in the realm. Directory remains 0700; the container's
    # non-root Keycloak UID must be able to read its explicitly mounted file.
    (RUNTIME / "scenescape-realm.json").chmod(0o644)
    if not state:
        # A previous config means an existing installation must explicitly migrate.
        state = {"mode": "legacy" if old else "native", "installed": False}
    save_state(state)
    log(f"Configuration saved; credentials preserved. Mode: {state['mode']}. UI: {public}")
    return config


def prepare(config):
    run(["make", "init-secrets"], env=environment(config))
    # Do not overwrite an existing deployment's generated/customized files.
    missing = [name for name in ("docker-compose.yml", ".env") if not (ROOT / name).exists()]
    if missing:
        run(["make", *missing], env=environment(config))
    (ROOT / ".env").chmod(0o600)
    secret_dir = Path(base_env().get("SECRETSDIR", ROOT / "manager/secrets"))
    key = secret_dir / "certs/scenescape-web.key"
    if not key.is_file():
        fail("Generated API TLS key is missing.")
    destination = RUNTIME / "native-web.key"
    private_write(destination, key.read_text())
    # Mount a read-only key file readable by API UID1000, beneath a private host directory.
    destination.chmod(0o444)
    compose(config, "config", "--quiet", native=True)


def build(config, args):
    doctor()
    prepare(config)
    if not args.skip_processing_build:
        log("Building tracking, Analytics and calibration images; no Django manager image")
        run(["make", "-j", str(args.jobs), "controller", "analytics", "autocalibration"], env=environment(config))
        run(["make", "install-models"], env=environment(config))
    log("Building native FastAPI and React images")
    compose(config, "build", "web", "modern-ui", native=True)


def wait_http(url, seconds=180):
    end = time.monotonic() + seconds
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < end:
        try:
            with opener.open(url, timeout=4) as result:
                if result.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(2)
    fail(f"Readiness failed at {url}. Inspect ./scenescape.sh logs; startup has NOT been declared successful.")


def kcadm(config, *args, data=None):
    # A per-call temporary config is deleted after reconciliation. Credentials
    # never appear in our output; Docker administrators are already privileged.
    result = compose(config, "exec", "-T", "keycloak", "/opt/keycloak/bin/kcadm.sh", *args,
                     "--config", "/tmp/scenescape-kcadm.config", native=True, capture=True, data=data, check=False)
    if result.returncode:
        fail("Keycloak reconciliation failed. Check saved bootstrap credentials and Keycloak logs; no users were deleted.")
    return result.stdout


def reconcile_identity(config):
    log("Reconciling Keycloak scopes and API audience without resetting users")
    try:
        kcadm(config, "config", "credentials", "--server", "http://127.0.0.1:8080/auth", "--realm", "master",
              "--user", config["KEYCLOAK_ADMIN_USERNAME"], "--password", config["KEYCLOAK_ADMIN_PASSWORD"])
        clients = json.loads(kcadm(config, "get", "clients", "-r", "scenescape", "-q", "clientId=scenescape-ui"))
        if len(clients) != 1:
            fail("Expected exactly one scenescape-ui client in the scenescape realm.")
        client = clients[0]["id"]
        scopes = json.loads(kcadm(config, "get", "client-scopes", "-r", "scenescape"))
        basic = next((s["id"] for s in scopes if s["name"] == "basic"), None)
        if not basic:
            fail("Keycloak's built-in basic scope is absent. Repair the realm before migration.")
        kcadm(config, "update", f"clients/{client}/default-client-scopes/{basic}", "-r", "scenescape")
        mappers = json.loads(kcadm(config, "get", f"clients/{client}/protocol-mappers/models", "-r", "scenescape"))
        mapper = {"name": "scenescape-api-audience", "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper",
                  "config": {"included.custom.audience": "scenescape-api", "access.token.claim": "true", "id.token.claim": "false"}}
        existing = next((m for m in mappers if m.get("name") == mapper["name"]), None)
        path = f"clients/{client}/protocol-mappers/models"
        if existing:
            mapper["id"] = existing["id"]
            kcadm(config, "update", path + "/" + existing["id"], "-r", "scenescape", "-f", "-", data=json.dumps(mapper).encode())
        else:
            kcadm(config, "create", path, "-r", "scenescape", "-f", "-", data=json.dumps(mapper).encode())
    finally:
        compose(config, "exec", "-T", "keycloak", "rm", "-f", "/tmp/scenescape-kcadm.config", native=True, capture=True, check=False)


def endpoints(config):
    print(f"\nSceneScape: {config['SCENESCAPE_PUBLIC_URL']}\nKeycloak administration: {config['SCENESCAPE_PUBLIC_URL']}/auth/admin/")
    if read_state().get("mode") == "native":
        print("Native mode: use your existing scenescape-realm user; no Django browser endpoint is served.")
    else:
        print("Legacy mode: the saved pre-cutover deployment is active.")


def start(config):
    native = read_state().get("mode") == "native"
    if not native:
        log("Starting the existing legacy deployment; use migrate-native for the single-UI backend")
        compose(config, "up", "-d", "--no-build", native=False)
        return
    if not read_state().get("installed"):
        fail("Native initialization is incomplete. Run install (fresh) or migrate-native (existing installation).")
    compose(config, "up", "-d", "--no-build", native=True)
    base = f"http://127.0.0.1:{config['MODERN_UI_PORT']}"
    wait_http(base + "/healthz")
    wait_http(base + "/api/v1/health")
    wait_http(base + "/auth/realms/scenescape/.well-known/openid-configuration")
    log("API, gateway and identity are responding. Check the Health page for live-feed status.")
    endpoints(config)


def wait_database(config):
    for _ in range(60):
        result = compose(config, "exec", "-T", "pgserver", "pg_isready", "-U", "scenescape", "-d", "scenescape",
                         native=True, capture=True, check=False)
        if result.returncode == 0:
            return
        time.sleep(2)
    fail("PostgreSQL did not become ready; no schema import was attempted.")


def initialize(config, fresh):
    # Only the native container can create its sscape_* schema. Old Django tables
    # are never altered or dropped by the native Alembic migration.
    compose(config, "up", "-d", "pgserver", "keycloak", native=True)
    wait_database(config)
    compose(config, "run", "--rm", "-T", "--no-deps", "web", "migrate", native=True)
    if fresh:
        run(["make", "init-sample-data"], env=environment(config))
        # Autocalibration uses the same UID and shared media volume in the release.
        compose(config, "run", "--rm", "--no-deps", "--user", "0:0", "--entrypoint", "sh", "web",
                "-c", "chown 1000:1000 /data/media", native=True)
        compose(config, "run", "--rm", "-T", "--no-deps", "web", "seed", "/data/samples/Retail.json", native=True)
    # Reconcile inside Keycloak before exposing the new UI or accepting writes.
    # No public gateway is required for an administrative CLI connection.
    for attempt in range(30):
        try:
            reconcile_identity(config)
            break
        except RuntimeError:
            if attempt == 29:
                raise
            time.sleep(3)


def backup(config):
    directory = RUNTIME / "backups" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, mode=0o700)
    for name in (*OLD_FILES, ".scenescape-modern.env"):
        source = ROOT / name
        if source.exists():
            private_write(directory / Path(name).name, source.read_text())
    # Record exact image IDs to make rollback independent of mutable image tags.
    rendered = json.loads(compose(config, "config", "--format", "json", native=False, capture=True).stdout)
    images = {}
    for name, service in rendered["services"].items():
        if service.get("image"):
            result = run(["docker", "image", "inspect", service["image"], "--format", "{{.Id}}"], capture=True, check=False)
            if result.returncode == 0:
                images[name] = result.stdout.decode().strip()
    private_write(directory / "rollback-images.json", json.dumps({"services": {name: {"image": image} for name, image in images.items()}}, indent=2))
    log("Exporting a stopped legacy application snapshot and database backup")
    compose(config, "up", "-d", "--no-deps", "pgserver", native=False)
    wait_database(config)
    with (directory / "legacy-snapshot.json").open("wb") as file:
        compose(config, "run", "--rm", "-T", "--no-deps", "--entrypoint", "python3", "web", "-",
                native=False, data=(ROOT / "tools/export_legacy.py").read_bytes(), output=file)
    # Parse before cutover: a warning on stdout must not masquerade as a snapshot.
    payload = json.loads((directory / "legacy-snapshot.json").read_text())
    if not isinstance(payload.get("scenes"), list) or "_migration" not in payload:
        fail("Legacy export did not produce a complete snapshot; no cutover was performed.")
    with (directory / "postgres.dump").open("wb") as file:
        compose(config, "exec", "-T", "pgserver", "sh", "-c",
                'export PGPASSWORD="$POSTGRES_PASSWORD"; exec pg_dump -h localhost -U scenescape -d scenescape -Fc --no-owner',
                native=False, output=file)
    project = config.get("COMPOSE_PROJECT_NAME", "scenescape")
    with (directory / "media.tar.gz").open("wb") as file:
        run(["docker", "run", "--rm", "--network", "none", "-v", f"{project}_vol-media:/data:ro",
             "alpine:3.23", "tar", "czf", "-", "-C", "/data", "."], output=file)
    for file in directory.iterdir():
        file.chmod(0o600)
    private_write(directory / "manifest.json", json.dumps({"source": "legacy", "counts": payload["_migration"]["counts"], "images": images}, indent=2))
    return directory


def migrate_native(config, args):
    if read_state().get("mode") == "native" and read_state().get("installed"):
        fail("Already migrated. Use build and restart; migration is not an update command.")
    doctor()
    if not args.yes:
        if input("This stops the stack, backs up data and replaces the Django runtime. Type MIGRATE: ") != "MIGRATE":
            fail("Migration cancelled.")
    # Build before downtime. Old UI/manager images have different tags and remain.
    build(config, args)
    if run(["docker", "image", "inspect", "alpine:3.23"], capture=True, check=False).returncode:
        run(["docker", "pull", "alpine:3.23"])
    compose(config, "stop", native=False)
    directory = None
    try:
        directory = backup(config)
        initialize(config, fresh=False)
        snapshot = (directory / "legacy-snapshot.json").read_bytes()
        compose(config, "run", "--rm", "-T", "--no-deps", "--entrypoint", "python", "web",
                "-m", "scenescape_api.migrate_legacy", "-", native=True, data=snapshot)
        state = {"mode": "native", "installed": True, "backup": str(directory.relative_to(ROOT)),
                 "migrated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        save_state(state)
        start(config)
    except BaseException:
        # Leave all data in place. No down -v, no reverse import, no database reset.
        compose(config, "stop", native=True, check=False)
        save_state({"mode": "legacy", "installed": True, "backup": str(directory.relative_to(ROOT)) if directory else None})
        compose(config, "up", "-d", "--no-build", native=False, check=False)
        raise
    print(f"\nMigration backup: {directory}\nSign out and back in once to obtain the new API audience claim.")


def rollback(config, args):
    state = read_state()
    directory = ROOT / state.get("backup", "")
    if not state.get("backup") or not (directory / "manifest.json").is_file():
        fail("No legacy cutover backup is recorded.")
    if not args.yes:
        print("Native changes made since migration are NOT written back to the old Django tables.")
        if input("Return to the pre-cutover data/UI? Type ROLLBACK: ") != "ROLLBACK":
            fail("Rollback cancelled.")
    compose(config, "stop", native=True)
    for name in OLD_FILES:
        source = directory / Path(name).name
        if source.is_file():
            private_write(ROOT / name, source.read_text())
    # Compose JSON is valid YAML. Pin recorded image IDs only for rollback.
    command = ["docker", "compose", "--project-directory", ROOT, "--env-file", ROOT / ".env", "-p", config["COMPOSE_PROJECT_NAME"],
               "-f", ROOT / "docker-compose.yml", "-f", ROOT / "sample_data/docker-compose.modern-ui-override.yml",
               "-f", directory / "rollback-images.json", "--profile", config["SCENESCAPE_PROFILE"], "up", "-d", "--no-build"]
    run(command, env=environment(config))
    state["mode"] = "legacy"
    save_state(state)
    print("Legacy runtime restored. Native tables, media and the backup are preserved; no data was deleted.")


def uninstall(config, args):
    if not args.yes and input("Delete this project's containers and operational volumes? Type UNINSTALL: ") != "UNINSTALL":
        fail("Uninstall cancelled.")
    native = read_state().get("mode") == "native"
    # Scope deletion to the active Compose project. Never invoke the upstream
    # clean targets, docker system prune, or a global list of exited containers.
    compose(config, "down", "--volumes", "--remove-orphans", native=native)
    print("Project containers and Compose volumes removed. Source, backups and local credentials are retained.")
    state = read_state()
    state["installed"] = False
    save_state(state)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Single SceneScape lifecycle entrypoint for WSL2/Linux")
    parser.add_argument("command", choices=["configure", "doctor", "build", "install", "migrate-native", "rollback-native", "start", "stop", "restart", "status", "logs", "open", "uninstall"])
    parser.add_argument("services", nargs="*")
    parser.add_argument("--port", type=int)
    parser.add_argument("--public-url")
    parser.add_argument("--admin-user")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--skip-processing-build", action="store_true", help="Reuse already-built tracking/Analytics/calibration images and models")
    parser.add_argument("--yes", action="store_true", help="Confirm migration/rollback/uninstall for unattended use")
    args = parser.parse_args()
    if args.jobs < 1 or args.jobs > 64:
        fail("--jobs must be between 1 and 64")
    if args.command == "doctor":
        doctor()
        return
    if args.command == "configure":
        configure(args)
        return
    config = load_config(False)
    if not config or "SCENESCAPE_API_SIGNING_KEY" not in config:
        if args.command in ("install", "build", "migrate-native"):
            config = configure(args)
        else:
            config = load_config()
    state = read_state()
    if not state:
        save_state({"mode": "legacy", "installed": True})
        state = read_state()
    if args.command == "build":
        if state.get("mode") != "native":
            fail("This is a legacy deployment. Use migrate-native, which backs it up before building/cutover.")
        build(config, args)
    elif args.command == "install":
        if state.get("mode") != "native":
            fail("Existing legacy configuration detected. Run migrate-native instead of resetting the installation.")
        build(config, args)
        initialize(config, fresh=not state.get("installed"))
        state["installed"] = True
        save_state(state)
        start(config)
    elif args.command == "migrate-native":
        migrate_native(config, args)
    elif args.command == "rollback-native":
        rollback(config, args)
    elif args.command == "start":
        doctor(); start(config)
    elif args.command == "stop":
        doctor(); compose(config, "stop")
        print("Stopped. All volumes, users, credentials and configuration are preserved.")
    elif args.command == "restart":
        doctor(); compose(config, "stop"); start(config)
    elif args.command == "status":
        doctor(); compose(config, "ps"); print(f"Runtime mode: {read_state().get('mode')}")
        endpoints(config)
    elif args.command == "logs":
        doctor(); compose(config, "logs", "-f", "--tail", "200", *args.services)
    elif args.command == "open":
        if shutil.which("wslview"):
            run(["wslview", config["SCENESCAPE_PUBLIC_URL"]])
        else:
            endpoints(config)
    elif args.command == "uninstall":
        doctor(); uninstall(config, args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. No volumes were implicitly removed.", file=sys.stderr)
        sys.exit(130)
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as error:
        # Do not print CalledProcessError.cmd, which may contain a credential.
        message = f"A subprocess exited with status {error.returncode}. Review the preceding diagnostic." if isinstance(error, subprocess.CalledProcessError) else str(error)
        print(f"ERROR: {message}", file=sys.stderr)
        sys.exit(1)
