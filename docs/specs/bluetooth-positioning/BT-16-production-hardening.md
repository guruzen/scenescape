# BT-16 — Production Hardening and Release

**Status:** PLANNED  
**Dependencies:** BT-13, BT-14, BT-15  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective
Qualify complete subsystem for supported production scale, resilience, security, upgrade and rollback.

## User stories
- Operator gets stable service.
- SRE can monitor/recover/upgrade/rollback.
- Security gets clear attack surface and evidence.

## Scope / functional requirements
1. Define supported scenes/anchors/tags/measurements-sec/update rate.
2. Load/soak/fault tests.
3. Bound queue/memory/storage/retention.
4. Helm resources/probes/PDB/affinity as needed.
5. Schema upgrade/downgrade + rollback runbook.
6. Backup/restore.
7. Metrics/dashboards/runbook.
8. Threat model and scans.
9. Privacy retention policy.
10. Operational feature flags.
11. Release notes/support matrix.

## Implementation design
- Separate scalable worker from control API.
- Horizontal ownership prevents duplicate solves.
- Idempotent processing where possible.
- One bad tag/provider cannot exhaust system.

## API, data and events
- Freeze/version supported contracts and deprecation policy.

## UX / operational behavior
- Final theme/accessibility/degraded-state regression.

## Security, privacy and failure handling
- Threat model covers spoof/replay/rogue gateway/location disclosure/secret leakage/DoS.
- Critical/high findings release-blocking until fixed/accepted by governance.

## Required tests
- [ ] Full unit/integration/E2E.
- [ ] Target-scale load.
- [ ] Soak.
- [ ] Worker/provider/MQTT/DB restart fault injection.
- [ ] Helm install/upgrade/rollback.
- [ ] Migration rollback.
- [ ] Security/vulnerability scan.
- [ ] Privacy regression.

## Evidence required
- [ ] Release readiness report.
- [ ] Performance/soak charts.
- [ ] Rollback evidence.
- [ ] Threat model/scans.
- [ ] Known limitations/support matrix.

## Acceptance criteria
- [ ] All prior acceptance passes.
- [ ] Scale meets documented targets.
- [ ] Upgrade+rollback demonstrated.
- [ ] No unresolved critical/high release issue.
- [ ] Runbook complete.
- [ ] Disable path preserves existing SceneScape.

## Out of scope
- Future providers beyond initial supported stack.

## Rollback / disable strategy
Documented Helm rollback and feature-disable path preserving DB/config.

## Implementation record
- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt
> Implement BT-16 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-16, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-16:`.
