# SceneScape - native operations workspace

**One React UI, one Keycloak sign-in, a Django-free API runtime.**

This fork is based on SceneScape **2026.2.0**. The `feature/react-keycloak-modern-ui` branch now contains a native FastAPI service and React workflows, rather than a React landing page that redirects users to Django. Existing tracking, Analytics, MQTT and calibration services remain separate components.

> **Engineering preview, not a completed parity release.** Core native workflows and the historian have automated coverage. Full WSL2/Docker/Keycloak/MQTT deployment and every advanced upstream workflow have not been validated in the development environment. Read [validation and remaining gaps](docs/ux/native/VALIDATION.md) before migrating an important installation.

![Native scene workspace, rendered against synthetic test data](docs/ux/native/scene-workspace.jpg)

*Screenshot of the actual React application using the native API and synthetic test observations. It is not a photograph, live camera feed, or proof of a deployed physical system.*

## Architecture

```text
React application                         Keycloak
  | native routes, protected media          | OIDC / PKCE
  | authenticated API / streaming fetch      |
  +---------------- FastAPI ----------------+
                       |
       configuration / incidents / media / replay
                       |
                   PostgreSQL
                       |
              historian / command worker
                       |
                existing MQTT broker
                       |
         SceneScape Analytics / tracking / cameras
```

The production API package `control-api/scenescape_api` does not import Django. Native mode replaces the Compose service named `web` with FastAPI; retaining that service name and its internal TLS endpoint avoids unnecessary changes to existing machine clients. The browser never navigates to that private endpoint or to a Django page.

## What is implemented

| Workspace | Native implementation |
| --- | --- |
| Live scenes | Authenticated scene/map loading, native 2D map with object positions, trails, cameras, regions and tripwires; a Three.js 3D viewer for self-contained GLB/image maps. Missing/stale observations are identified explicitly. |
| Configuration | Native CRUD for scenes, cameras, sensors, regions, tripwires, assets, child-scene links and calibration markers; typed validation and revision checks. Advanced fields currently use a schema-guided JSON editor. |
| Geometry | Draw polygons and directional boundaries, edit coordinates, validate geometry, save to the native API and publish configuration-change commands through an outbox. |
| Calibration | Manual poses, 2D/3D point correspondence, camera-frame requests and integration endpoints for the existing autocalibration service. |
| History | Sampled Analytics observations, event-time queries, retained configuration snapshots, metadata replay, occupancy/crossing/dwell summaries and CSV export. |
| Incidents | Convert an analytics event to a durable incident; acknowledge, investigate, assign, add notes, resolve and reopen with an audit record. |
| Identity | Keycloak Authorization Code + PKCE, server-side token issuer/audience/expiry checks, application roles and optional scene scopes; separate machine credential compatibility. |
| Appearance | Light, Light Air, Dark and Dark Command, with persistent selection and layout/density variations. |

There is no fake live-object animation, invented historical trend, hidden Django iframe or automatic browser handoff in the native application. A missing upstream service is an error/unavailable state, not a working feature.

### Important parity boundaries

The current native implementation is not a drop-in replacement for every specialized manager feature. Advanced geospatial map rendering, mesh reconstruction workflows, full remote-child forwarding, Kubernetes pipeline/model orchestration and some specialized calibration operations still require parity work. The native 3D viewer does not reproduce every visualization feature of the upstream renderer. Legacy snapshot validation deliberately fails rather than silently discarding unsupported configuration.

Historical metadata is not a video recorder. Automated notification delivery/escalation, a complete alert-rule evaluator, HA failover and production-scale historian performance qualification are not included. See the detailed [capability and validation record](docs/ux/native/VALIDATION.md).

## Existing WSL2 installation: migrate explicitly

Do **not** uninstall your working deployment or delete its volumes.

```bash
git switch feature/react-keycloak-modern-ui
git pull --ff-only
./scenescape.sh doctor
./scenescape.sh migrate-native --skip-processing-build
```

`--skip-processing-build` reuses the tracking, Analytics, calibration images and models you already built. Omit it when those images are unavailable. The migration still builds the native API and UI.

The command asks you to type `MIGRATE`, stops the old stack, exports its configuration using a one-shot old manager container, backs up PostgreSQL and media, imports into separate native tables, reconciles the Keycloak client without deleting users, and starts native mode. The old Django HTTP server does not run in native mode. Failed cutover attempts do not delete old data or volumes.

Backups are private files under `.scenescape-runtime/backups/`. They can contain credentials and media. Never commit or share them. After migration, sign out and back in once so your access token includes the new `scenescape-api` audience.

[Full installation, migration and recovery guide](docs/user-guide/get-started/installation.md)

## Fresh WSL2 installation

Use a normal WSL2 Linux user, Docker Desktop's Linux engine with WSL Integration, Docker Compose **2.24.4 or later**, Python 3, Make and OpenSSL. Prefer a checkout in `~/src/scenescape` rather than `/mnt/c`.

```bash
./scenescape.sh configure
./scenescape.sh install
./scenescape.sh status
```

Open `http://localhost:8088`. The script generates distinct random credentials; the Keycloak bootstrap administrator is not an everyday application user. Create a user in realm `scenescape`, assign `scenescape-viewer` or `scenescape-admin`, and sign into the application with that user.

All normal operations use the same entrypoint:

```bash
./scenescape.sh start
./scenescape.sh stop
./scenescape.sh restart
./scenescape.sh logs web native-worker modern-ui
./scenescape.sh build --skip-processing-build
```

`stop` preserves data. `uninstall` explicitly deletes this Compose project's operational volumes after confirmation; it is **not** an update or troubleshooting command. Backups and local credentials are retained by the uninstall helper.

## Source layout

```text
control-api/                         FastAPI, schema migrations, collector and tests
modern-ui/src/native/                Native operator and configuration workflows
modern-ui/tests/                     Isolated browser harness; not production auth
sample_data/docker-compose.native-override.yml
scenescape.sh                        One lifecycle command for WSL2/Linux
tools/native_runtime.py              Build, migration, start/stop and recovery
tools/export_legacy.py               One-time export inside the old image only
kubernetes/scenescape-native/         Native API/worker/UI chart with external dependencies
docs/ux/native/                      Screenshots, validation and implementation boundaries
```

The original upstream manager sources and chart remain in Git for reference and explicit rollback. Their presence in the source tree does not mean a Django server is started in native mode.

## Tests

```bash
cd control-api
python3 -m pip install -r requirements.txt -r requirements-test.txt
PYTHONPATH=. pytest -q

cd ../modern-ui
npm ci
npm run build
```

The browser test uses real React components and the native API with an isolated SQLite fixture and a test-only identity adapter. It does **not** validate real Keycloak PKCE, a physical camera or an MQTT broker. Instructions and limitations are in [VALIDATION.md](docs/ux/native/VALIDATION.md). Production builds do not import the test identity adapter.

## Kubernetes

Use [kubernetes/scenescape-native](kubernetes/scenescape-native/README.md) for the native API, worker and UI. That chart requires existing PostgreSQL, Keycloak, MQTT, media storage and processing services. It is deliberately not an in-place replacement chart for an existing upstream Helm release: upgrading an umbrella release with a smaller chart could delete unrelated resources.

## Upstream and license

Upstream project: [open-edge-platform/scenescape](https://github.com/open-edge-platform/scenescape). This is an independent modernization branch, not an upstream release. Existing licenses and attribution remain applicable; see [LICENSE](LICENSE) and upstream documentation under `docs/`.
