# BT-12 — Real Channel Sounding Provider

**Status:** BLOCKED
**Blocker:** Real Channel Sounding hardware/vendor SDK and HIL environment are not available in the repository.  
**Dependencies:** BT-06, BT-10, BT-11  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Integrate one real Channel Sounding hardware stack through the provider abstraction.

## User stories

- Installer commissions supported hardware.
- System receives normalized real ranges/telemetry.
- Support sees capacity/session health.

## Scope / functional requirements

1. Document supported hardware/firmware/SDK.
2. Implement RangingProvider.
3. Map provider IDs to SceneScape IDs.
4. Configure initiator/reflector roles.
5. Expose session capacity/update rate/failures.
6. Normalize range quality/PBR/RTT diagnostics when available.
7. Telemetry integration.
8. Reconnect recovery.

## Implementation design

- SDK isolated in adapter/process.
- No vendor types in core contracts.
- Scheduler handles session limits.
- Secrets via secure deployment config.

## API, data and events

- Core measurement/device contracts unchanged.
- Provider-specific admin only if unavoidable.

## UX / operational behavior

- Connected/ranging/unavailable/capacity-limited diagnostics.

## Security, privacy and failure handling

- Service identity/MQTT ACL.
- Secure pairing keys.
- License/dependency/vulnerability review.

## Required tests

- [ ] HIL smoke.
- [ ] Multi-tag scheduling.
- [ ] Reconnect/reboot.
- [ ] Known-distance sanity.
- [ ] Telemetry.
- [ ] Capacity saturation.
- [x] Simulator regression.

## Evidence required

- [ ] Hardware/firmware/SDK BOM.
- [ ] Known-distance samples.
- [ ] HIL output.
- [ ] Security scan.

## Acceptance criteria

- [ ] Real measurements flow through solver/tracker.
- [x] Core contracts unchanged.
- [ ] Recovery graceful.
- [ ] Capacity visible.

## Out of scope

- Second vendor.
- Final accuracy claim.

## Rollback / disable strategy

Disable provider deployment; core/simulator remain.

## Implementation record

- Implementation commits: `3f7028167350`, `ee2b56c63840`, `0a822f95f10d`
- Evidence: `.github/evidence/bluetooth-positioning/BT-12-real-channel-sounding-provider.md`
- Known deviations: The vendor-neutral adapter boundary, scheduler, telemetry normalization and reconnect contracts are implemented and software-tested. No concrete vendor adapter or real Channel Sounding HIL evidence exists, so hardware-specific tests/acceptance remain blocked.

## Continuation prompt

> Implement BT-12 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-12, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-12:`.
