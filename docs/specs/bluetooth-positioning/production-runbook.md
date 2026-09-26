# Bluetooth Positioning Production Runbook

## Release status

This runbook covers the production operation of the SceneScape Bluetooth
positioning software stack implemented through BT-16.

A software build is not, by itself, a production accuracy qualification.
BT-12 must identify and validate a real Channel Sounding hardware/firmware/SDK
stack, and BT-13 must qualify that stack at real sites before any high-accuracy
product claim is released.

## Feature flags

The native Helm chart is fail-closed for Bluetooth:

- `bluetooth.enabled=false` by default.
- `bluetooth.telemetryEnabled=false` by default.
- `bluetooth.spatialEventsEnabled=true` only takes effect when positioning is enabled.
- `bluetooth.fusionEnabled=false` by default.

Disabling positioning stops new range ingestion/processing and removes
Bluetooth objects and anchors from normal Live/Bundle projections. It does not
delete anchors, tags, assignments, calibration revisions, survey data, raw
history, or tracked history.

## Deployment

### Single worker

Use one worker when provider volume fits one process:

```yaml
worker:
  replicas: 1
bluetooth:
  enabled: true
  telemetryEnabled: true
mqtt:
  clientId: scenescape-native-historian
```

### Multiple workers

Multiple workers require an MQTT shared-subscription group. The chart rejects
`worker.replicas > 1` without it.

```yaml
worker:
  replicas: 3
mqtt:
  clientId: scenescape-native-historian
  sharedSubscriptionGroup: scenescape-bt-workers
bluetooth:
  enabled: true
  telemetryEnabled: true
```

Each pod receives a unique MQTT client-ID suffix from its pod name. Shared
subscriptions ensure one copy of a message is owned by one worker rather than
being solved by every replica.

## Capacity and scaling

There are two independent capacity ceilings:

1. SceneScape software processing capacity, measured by the deterministic
   BT-16 benchmark and deployment load tests.
2. Provider/radio capacity, exposed by the BT-12 provider adapter as
   `max_sessions` and `max_update_hz`.

The supported production envelope is the lower of these limits. Do not infer
radio/session scale from solver benchmark results.

The CI benchmark command is:

```bash
PYTHONPATH=control-api python -m scenescape_api.bluetooth_benchmark \
  --tags 20 --anchors 4 --hz 5 --duration 5 --noise-stddev-m 0.05
```

This represents 100 requested position fixes/s and 400 synthetic range
observations/s. Thresholds are set only after repeated runner evidence is
recorded.

## Health and metrics

Worker probes execute:

- readiness: `python -m scenescape_api.cli worker-ready`
- liveness/startup: `python -m scenescape_api.cli worker-health`

Readiness requires a current MQTT heartbeat in `connected` state. Liveness
also accepts `connecting` and `degraded` so transient provider/DB faults do
not trigger unnecessary restart loops.

Service-auth metrics:

```text
GET /api/v2/bluetooth/metrics
Authorization: Token <service-token>
```

Metrics are intentionally aggregate and contain no scene, tag, anchor,
assignment, person, or provider labels. Important series include ingress
accepted/rejected counts, queue drops/depth, active tracks, raw row count,
pipeline/tracker/spatial counters, and retention policy.

Browser diagnostics remain scene/admin scoped through the existing OIDC
control plane.

## Retention

The chart schedules a `CronJob` every 15 minutes by default. Retention is
independent by data class:

- normalized raw ranges: 1 day
- raw solver positions: 1 day
- tracked positions: 7 days
- device telemetry: 7 days

Control-plane configuration, tag assignment history, calibration revisions,
and survey configuration are not removed by this retention job.

Environment overrides:

```text
BLUETOOTH_RAW_RETENTION_S
BLUETOOTH_RAW_POSITION_RETENTION_S
BLUETOOTH_TRACKED_POSITION_RETENTION_S
BLUETOOTH_DEVICE_TELEMETRY_RETENTION_S
```

Run cleanup manually with:

```bash
python -m scenescape_api.cli retention
```

## Backup

Before upgrade or before a deliberate destructive schema operation:

1. Back up PostgreSQL with the organization's approved `pg_dump` procedure.
2. Record the application image tag, Helm release revision and Bluetooth
   feature values.
3. Record provider adapter version, hardware/firmware/SDK BOM when BT-12 is
   enabled.
4. Protect the backup according to precise-location/privacy policy.

Bluetooth control-plane and high-rate tables use the
`native_bluetooth_*` prefix.

## Upgrade

1. Keep Bluetooth disabled for a first migration into an existing deployment.
2. Back up PostgreSQL.
3. Deploy the new API; additive migrations create Bluetooth tables.
4. Verify API health and existing vision/sensor SceneScape behavior.
5. Commission providers/anchors/tags/calibration.
6. Enable telemetry, then positioning.
7. Verify worker readiness, queue depth, rejection rate, position quality and
   stale counts.
8. Enable spatial events/fusion only after base positioning is stable.

## Rollback

Preferred rollback is non-destructive:

1. Set `bluetooth.enabled=false`,
   `bluetooth.telemetryEnabled=false`, and
   `bluetooth.fusionEnabled=false`.
2. Roll back the Helm release/application image.
3. Leave additive Bluetooth tables in PostgreSQL.
4. Verify existing vision/sensor Live, history, incidents and configuration.
5. Investigate using preserved Bluetooth history/config.

Physical schema removal is not required for application rollback. The
`downgrade_all_bluetooth` helper refuses to drop any populated Bluetooth
table unless `allow_data_loss=True` is explicitly supplied. Use physical
drop only in controlled test/disaster-recovery procedures after backup and
governance approval.

## Fault response

### MQTT/provider outage

- Old fixes age through good/degraded/predicted/stale/unavailable.
- Worker readiness becomes false if MQTT is disconnected.
- No fabricated position is emitted.
- Provider scheduler reconnect/requeues sessions with bounded backoff.

### Queue pressure

- Accepted raw measurement is persisted before solver handoff.
- Solver queue is bounded.
- Queue drops are counted and observable.
- Scale workers only with a shared-subscription group.

### Bad calibration

- Geometry warnings/GDOP diagnostics identify weak layouts.
- Publish is revisioned.
- Restore a retired calibration revision; do not edit history in place.

### Database pressure/outage

- Worker heartbeat can enter degraded state.
- Do not increase MQTT/session rates until database health and queue depth are
  stable.
- Retention prevents unbounded high-rate table growth.

### Low battery/offline device

Use battery provenance/freshness and operational health. Missing Battery
Service is not equivalent to 0% and does not block commissioning.

## Privacy

Precise movement and person/tag assignment are privacy-sensitive.

- Browser access remains OIDC- and scene-scoped.
- Person/tag assignment is versioned and auditable.
- Aggregate metrics contain no precise identifiers.
- High-rate position retention is bounded separately from configuration.
- BT-15 fusion associates tracks only from spatial/temporal evidence and does
  not perform biometric identity inference.
- Qualification logs should use minimized/anonymized identifiers wherever
  policy permits.

## Release gate

Production release requires all of the following:

- software unit/integration/E2E gates green
- BT-16 load/soak/fault/rollback evidence
- current security/vulnerability scans with no unresolved critical/high issue
- BT-12 real provider HIL/BOM/security evidence
- BT-13 real-site static/dynamic/NLOS/repeatability qualification
- explicit support matrix based on those measurements
