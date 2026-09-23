# BT-10 — Device and Battery Telemetry

**Status:** PLANNED  
**Dependencies:** BT-02, BT-06  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Populate trustworthy battery/device/firmware health from standard Bluetooth services or vendor adapters.

## User stories

- Operator sees battery/last seen.
- Admin sees model/firmware/serial provenance.
- Support knows telemetry source.

## Scope / functional requirements

1. Battery Service normalization.
2. Device Information Service normalization.
3. Vendor telemetry adapter.
4. Manual/QR fallback.
5. source+observed_at.
6. Configurable warning/critical battery.
7. Bound polling/cache.

## Implementation design

- DeviceTelemetryProvider.
- Gateway/provider collection, not browser BLE.
- Unknown != 0.
- Telemetry storage separate from stable config.

## API, data and events

- Device MQTT + read summaries; writes service-auth.

## UX / operational behavior

- Display battery/firmware freshness and low/stale/unknown.

## Security, privacy and failure handling

- No pairing secrets.
- Scene scope.
- Polling protects tag battery.

## Required tests

- [ ] Standard service fixtures.
- [ ] Vendor fixture.
- [ ] Unknown/stale/0% distinction.
- [ ] Thresholds.
- [ ] Permissions.
- [ ] Cache/polling.

## Evidence required

- [ ] UI screenshots.
- [ ] Normalized samples.
- [ ] Tests.

## Acceptance criteria

- [ ] Battery has provenance/freshness.
- [ ] Missing standard service does not block commissioning.
- [ ] Low-battery state works.
- [ ] No secrets.

## Out of scope

- Firmware OTA.
- Proprietary commissioning beyond adapter.

## Rollback / disable strategy

Disable telemetry provider; previous values become stale.

## Implementation record

- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt

> Implement BT-10 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-10, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-10:`.
