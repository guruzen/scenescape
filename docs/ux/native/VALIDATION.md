# Native implementation: validation and remaining parity work

This branch now has actual native API/UI code, not just a UX prototype. It is nevertheless an **engineering preview**. A complete replacement must pass real processing-service contracts and an operational cutover before the old image/backup can be retired.

## Executed checks

The machine-readable `validation-results.json` alongside this file records the latest local test outcomes. Backend tests use SQLite and isolated credentials. Browser tests use the real React components and native API, with synthetic observations and a substituted test-only identity adapter. The production frontend imports the real Keycloak provider, not that adapter.

Checks cover token validation and scene permissions; resource CRUD/revision checks; geometry validation; safe protected media; sampling/replay gaps; incident actions; transaction rollback and import identity preservation; bounded ZIP transfers; local configuration credential preservation; explicit migration safety; theme selection/persistence; native scene navigation; geometry save; calibration pose save; history/trends and incident actions in a browser; and mobile overflow.

The actual 3D rendering check was skipped when the test browser could not create WebGL2. The native error/fallback path was tested instead. A successful TypeScript/Vite build is not proof of a working GPU renderer.

## Not executed in this environment

A full WSL2 + Docker Desktop installation; building/running every upstream processing image; actual Keycloak PKCE/browser logout; an actual MQTT broker and physical camera pipeline; old-manager export inside its real image; PostgreSQL-specific concurrency/migration behavior; live autocalibration service operations; production-scale retention/load; and Kubernetes deployment have not been exercised here. Treat the lifecycle and deployment code as requiring a staged installation test, not a production certification.

## Working native surfaces vs specialized gaps

| Area | Implemented in code | Remaining qualification/parity work |
| --- | --- | --- |
| Scene viewing | Native 2D, protected maps, live observations, trails/geometry/camera layers; Three.js GLB/image viewer | Actual GPU verification; all upstream 3D interactions and asset rendering parity |
| Configuration | Native typed resource CRUD, schema-driven advanced fields, revision checks, notification outbox | Dedicated UX for every advanced field; every upstream side effect and serialization edge case |
| Geometry | Polygon/tripwire authoring and validation, persisted configuration snapshots | All volumetric editing/visualization affordances and specialized region options |
| Calibration | Manual pose, point-correspondence calculations, camera-frame requests and integration endpoints for the existing autocalibration service | End-to-end physical calibration; all specialized intrinsics/LiDAR/markerless workflows |
| Import/migration | JSON/ZIP bundles, IDs retained, validation in one transaction, backup/rollback tooling | Actual full legacy export fixture coverage, very large imports, filesystem crash recovery |
| Live/history | Regulated Analytics ingestion, events, sampling, replay and coverage gaps | Broker outage/recovery tests, HA collector design, performance/retention sizing |
| Incidents | Owned incident records and action/audit lifecycle | Full rule evaluator, automatic notification delivery/escalation and external integrations |
| Advanced manager features | Fields/assets/child links represented as native resources | Geospatial map rendering, mesh reconstruction, complete remote-child forwarding and Kubernetes pipeline/model orchestration |
| Security | JWT signature/issuer/audience/expiry, roles/scopes, protected media, bounded uploads, TLS upstream verification | External penetration testing, deployment threat review, secret rotation, tenancy/HA qualification |

Metadata replay is **not recorded video playback**. The code does not manufacture historical footage or physical camera data. Samples/CSV averages are based on retained observations, not an assertion of uninterrupted coverage.

## Reproducing backend and browser checks

```bash
cd control-api
python3 -m pip install -r requirements.txt -r requirements-test.txt
PYTHONPATH=. pytest -q
```

For browser checks, start these two isolated processes in separate terminals:

```bash
# Terminal 1, from control-api:
PYTHONPATH=. python tests/browser_server.py

# Terminal 2, from modern-ui:
npm ci
npx vite --config vite.native-tests.config.ts
```

Then from `modern-ui`, with Python Playwright and a Chromium browser installed:

```bash
CHROMIUM_PATH=/path/to/chromium python tests/browser_checks.py
```

Restart the isolated API fixture before rerunning: the tests intentionally modify its synthetic configuration and incidents. Never run the fixture server against a real database. The fixture creates its own temporary SQLite database and synthetic credentials; it is not included in the production Docker build.

## Cutover acceptance

Before calling this a complete manager replacement, verify that a migrated installation runs with no Django HTTP server, can perform the required native workflows, publishes configuration changes seen by the tracking/Analytics services, preserves media/IDs/permissions, and handles expired identity and missing feeds correctly. Keep the pre-cutover backup and image IDs until this is demonstrated. Native changes are not automatically backported on rollback.
