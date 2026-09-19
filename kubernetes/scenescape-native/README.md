# Native API / UI Helm deployment

This chart deploys **FastAPI + one historian/command worker + React/Nginx**, with no Django image or HTML views. It is a separate native chart, not an in-place upgrade of the upstream monolithic chart. It requires an existing PostgreSQL database, MQTT broker, Keycloak realm and shared media PVC. Tracking, Analytics, inference pipelines and calibration services remain separate SceneScape components.

**Cluster cutover has not been exercised in this build environment.** Do not run `helm upgrade` of an existing SceneScape release with this chart: resources omitted from that release could be removed. Create an isolated native release, import a snapshot into a separate/test database first, and move processing-service REST URLs only after validating the native `/api/v1` contract. WSL2 migration is handled separately by the root lifecycle script.

## Required inputs

Provide `runtimeSecret` with `DATABASE_URL` (PostgreSQL SQLAlchemy URL, URL-encoded credentials) and `API_SIGNING_KEY` (at least 32 random characters); `serviceAuthSecret` with the existing JSON `controller.auth`, `browser.auth` and `calibration.auth`; `tls.existingSecret` with internal API `tls.crt`, `tls.key`, `ca.crt`; and a shared `media.existingClaim`. `tls.serverName` must match the internal API certificate. Supply `mqtt.host`, `mqtt.caSecret`, and the external Keycloak issuer/browser URL. Do not place secret values in Git or Helm command-line arguments.

The Keycloak public browser client must use Authorization Code + PKCE S256, have the default `basic` scope, and an `oidc-audience-mapper` that adds `scenescape-api` to **access tokens only**. The realm template under `modern-ui/keycloak/` contains this mapper. Add it non-destructively in existing realms; importing a realm at startup does not replace one already in the database.

```bash
helm lint kubernetes/scenescape-native -f /secure/native-values.yaml
helm template scenescape-native kubernetes/scenescape-native \
  -f /secure/native-values.yaml > /secure/native-rendered.yaml
helm install scenescape-native kubernetes/scenescape-native \
  -f /secure/native-values.yaml --wait --timeout 10m
```

Do not commit rendered manifests. The native schema migration is an API init container. It creates only `sscape_*` tables and the native Alembic revision table, not Django tables. A legacy resource snapshot must be imported explicitly before changing the tracking services' REST endpoint. Back up PostgreSQL and media first. Existing service credentials authenticate at the private `/api/v1/auth`; the browser gateway deliberately blocks that endpoint.

`/api/v2/events/stream/{scene}` uses an authenticated streaming fetch with no token in the URL. The ingress must permit long-lived responses without buffering. The API validates bearer expiry and scene permissions, including media/replay. Nginx validates the API's internal TLS CA and server name.

Use a RWX media PVC where API, calibration and processing pods can be scheduled on different nodes. Keep a single historian worker per MQTT client ID. This initial chart deliberately deploys one API replica with `Recreate`; it is not an HA/rolling-schema-upgrade design.

Run core service contract tests, actual MQTT/frame/calibration tests and a staged cutover before production. The chart does not provision inference pipelines, an identity server, storage backups, a video recorder, notification delivery or production monitoring.
