# Installation and migration: native UI and API

This guide applies to `guruzen/scenescape`, branch `feature/react-keycloak-modern-ui`, based on SceneScape 2026.2.0. **Native mode serves one React application with a FastAPI backend. There is no Django login or fallback page in normal navigation.** The original source and an explicit rollback path remain available.

The implementation is an engineering preview. Read [validation and parity boundaries](../../ux/native/VALIDATION.md) before migrating important data. Automated local tests are not a substitute for a clean WSL2 deployment test.

## Prerequisites on WSL2

Use an Ubuntu WSL2 distribution and a normal Linux user, not `sudo` to run the lifecycle script. Start Docker Desktop with its Linux engine and enable **Settings > Resources > WSL Integration** for that distribution. Required tools are Docker Compose 2.24.4+, Python 3, Make and OpenSSL. The native overlay uses Compose's explicit `!override` semantics so old Django ports, commands and secret mounts are not accidentally retained.

Keep the checkout on the Linux filesystem where practical:

```bash
mkdir -p ~/src
cd ~/src
git clone --branch feature/react-keycloak-modern-ui https://github.com/guruzen/scenescape.git
cd scenescape
./scenescape.sh doctor
```

The installer does not install or reconfigure Docker Desktop, Windows, WSL, drivers or system packages. Docker/npm/Python registries must be reachable for the first build. Existing upstream [system requirements](system-requirements.md) still apply to tracking/inference workloads.

## A. You already installed the earlier React + Django version

**Do not run `uninstall`, `docker compose down -v`, `make demo-close` or any global Docker prune.** Those are not migration steps.

Close other users' configuration sessions and run from the repository:

```bash
git switch feature/react-keycloak-modern-ui
git pull --ff-only
./scenescape.sh doctor
./scenescape.sh migrate-native --skip-processing-build
```

The last option reuses existing processing images/models. Omit it to rebuild tracking, Analytics and calibration as well. The new API and UI are always built. The helper asks you to type `MIGRATE`; `--yes` is available only for deliberately unattended migration.

### What the migration does

It builds before downtime, stops the old stack, starts only PostgreSQL for export, and runs the old manager image **once as an export tool**, not as a web server. A transactional snapshot preserves scene/camera/sensor/geometry/asset identifiers. A `pg_dump` backup, media archive, original configuration files and exact old image IDs are recorded under:

```text
.scenescape-runtime/backups/<UTC timestamp>/
```

It then creates separate `sscape_*` tables, validates/imports the snapshot, attaches Keycloak's `basic` scope and a `scenescape-api` access-token audience mapper, and starts the native stack. The existing PostgreSQL volume and Keycloak users are not reset. Unsupported or inconsistent legacy configuration causes an error rather than partial/silent data loss.

The Compose service named `web` is now the native API. It retains the private `https://web.scenescape.intel.com:443/api/v1` endpoint for existing processing clients; it does not serve Django pages. Its former host port 443 is removed. The React gateway at port 8088 handles browser access and validates the API's internal TLS CA.

After cutover, **sign out and sign in again** to receive the new audience claim. Old access tokens remain old tokens until replaced.

### Check the result

```bash
./scenescape.sh status
./scenescape.sh logs web native-worker modern-ui
```

Open `http://localhost:8088`. Open a scene from the overview: it should remain inside React with native 2D/3D, geometry and calibration tabs. Check **Health** for MQTT/worker state and last observations. An HTTP-ready API does not by itself prove cameras or the collector are producing data.

Do not interpret an empty scene as successful tracking. Confirm an actual input, calibration, Analytics observation and event against the intended physical/test scenario.

### Recovery

Migration failures preserve old volumes and attempt to restart the legacy deployment. Read the actual error; do not delete volumes to make the installer continue. If the export cannot load the old image/settings, or legacy configuration is rejected, keep the backup and resolve that incompatibility first.

After a successful cutover, an explicit rollback is available:

```bash
./scenescape.sh rollback-native
```

Type `ROLLBACK` when prompted. It restores the old runtime and pre-cutover configuration using recorded image IDs. **Changes made in the native database after migration are not copied back to Django.** Native tables and backups are retained; rollback is not a bidirectional data synchronization feature. Do not delete rollback images until the native installation has been accepted.

## B. Fresh installation

```bash
./scenescape.sh configure
./scenescape.sh install
```

The initial build creates processing images/models, the native API image and the UI image, initializes schema/sample data and starts the stack. No Django manager image is built for this native path. Some upstream secret-generation tooling remains in the source tree for service compatibility.

Defaults:

```text
Application:         http://localhost:8088
Keycloak management: http://localhost:8088/auth/admin/
```

For a different local port, configure it before installation:

```bash
./scenescape.sh configure --port 8090
./scenescape.sh install
```

The script generates matching client redirect URLs. Remote HTTP is rejected. A remote HTTPS origin requires a separately configured, trusted TLS reverse proxy; selecting an HTTPS URL does not create that proxy or certificate. An installed issuer is not silently changed by `configure`.

## First Keycloak user

The bootstrap administrator credentials are in the private `.scenescape-modern.env` file. Read them locally; do not paste the file into an issue or chat:

```bash
grep -E '^KEYCLOAK_ADMIN_(USERNAME|PASSWORD)=' .scenescape-modern.env
```

Use those credentials at the Keycloak management URL. Select the **scenescape** realm, not `master`. Create an application user, set their password, and assign `scenescape-viewer` or `scenescape-admin`. Sign into the React application with that user. Existing users are preserved during migration.

The public client `scenescape-ui` uses Authorization Code with PKCE S256. Password grants and implicit flow are disabled. The default `basic` scope supplies the subject claim; the dedicated audience mapper adds `scenescape-api` to access tokens, not ID tokens. The API checks signature, issuer, audience, subject and expiry. Media/history/stream access uses the same authorization rather than a second browser session.

The local embedded Keycloak uses `start-dev` for evaluation. Production requires an appropriately hardened identity deployment, trusted TLS, backups and operational controls; these are not supplied by a demo Compose file.

## Daily lifecycle

```bash
./scenescape.sh start
./scenescape.sh stop
./scenescape.sh restart
./scenescape.sh status
./scenescape.sh logs web native-worker modern-ui
./scenescape.sh open
```

`stop` preserves data and credentials. After a native code update:

```bash
git pull --ff-only
./scenescape.sh build --skip-processing-build
./scenescape.sh restart
```

An old hybrid installation deliberately refuses the new normal build/install path until explicitly migrated. This prevents a new frontend from being placed over an incompatible old backend without a backup.

## Uninstall

```bash
./scenescape.sh uninstall
```

This asks for `UNINSTALL`, then removes **this Compose project's** containers and operational volumes, including PostgreSQL and Keycloak data. It does not prune unrelated Docker projects. Source, backups and local credentials are retained. `--yes` skips the confirmation and must not be used as a routine recovery step.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Docker unavailable | Start Docker Desktop and enable this WSL distribution; use Linux containers. |
| `!override` parsing error | Update Docker Compose to 2.24.4 or later. |
| Missing `sub` or audience | Reconcile the correct Keycloak client, then sign out/in. Do not disable JWT claim verification. |
| API TLS verification error | The mounted CA and `SCENESCAPE_API_SERVER_NAME` must match the API certificate. Do not fix this by disabling verification. |
| Migration validation failure | Keep the stopped/exported snapshot and backup; unsupported fields are rejected rather than discarded. The script attempts legacy recovery. |
| Media permission error | API UID 1000 needs read access to existing maps and write access to `native-uploads`; avoid recursively changing ownership of all old media without review. |
| No live objects | Check native worker MQTT connectivity, Analytics regulated output, scene IDs and timestamps; API readiness alone is insufficient. |
| Camera/auto-calibration request fails | Confirm the corresponding upstream camera/calibration service and TLS/credentials. Native forms cannot create an unavailable upstream capability. |
| No WebGL2 | Use native 2D; the application does not redirect to Django. GPU/WSL/browser configuration is separate from the API. |

## Kubernetes

The separate [native Helm chart](../../../kubernetes/scenescape-native/README.md) deploys API/worker/UI against external PostgreSQL, Keycloak, MQTT and media storage. Do not substitute it in an existing umbrella release with `helm upgrade`: omitted resources could be deleted. Use an isolated release and a staged migration/contract test first. The root WSL2 script is a Compose lifecycle tool, not an automatic Kubernetes migration controller.
