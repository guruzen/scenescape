# Bluetooth Positioning Threat Model

## Assets

- precise tag/person/asset location and history
- tag-to-entity assignment history
- anchor calibration and survey data
- provider/radio session control
- service credentials, pairing material and vendor SDK secrets
- incident/spatial-event integrity

## Trust boundaries

1. Browser/OIDC control plane.
2. Provider/gateway adapter process.
3. MQTT/service-auth ingest boundary.
4. Native worker and solver/tracker.
5. PostgreSQL high-rate/control-plane storage.
6. Live/history/incident projection.
7. Optional BLE/vision fusion.

## Threats and controls

| Threat | Concrete risk | Implemented controls | Residual release action |
| --- | --- | --- | --- |
| Spoofed range/telemetry | false position or battery state | service auth, provider ID binding, commissioned anchor/tag checks, scene cross-check, MQTT TLS/ACL design | validate real provider identity/ACL in BT-12 HIL |
| Replay/duplicate traffic | stale coordinate accepted as current | source timestamp/replay window, provider/session/sequence uniqueness, out-of-order rejection | verify vendor sequence/session behavior in BT-12 |
| Rogue/compromised gateway | valid credential emits malicious measurements | provider-scoped identity, residual/quality/NLOS handling, observable rejects | credential rotation and gateway hardening per vendor |
| DoS / oversized input | worker memory/CPU exhaustion | bounded payload/provider details, bounded solver queue, rate/capacity scheduler, retention, metrics | load/soak and external rate limiting as deployment requires |
| Duplicate solving in scale-out | duplicate positions/events | unique pod MQTT client IDs + shared subscriptions; chart rejects unsafe replicated mode | validate broker shared-subscription semantics in deployment |
| Location disclosure | precise people/assets exposed | scene scope, admin restrictions for assignments, bounded history, aggregate unlabeled metrics | organization privacy/DPIA and role review |
| Secret leakage | pairing/API secret returned to browser/log | secrets mounted outside resource payloads; provider adapter secrets file; secret fields rejected | vendor SDK/logging review in BT-12 |
| Calibration tampering | systematically wrong positions | admin-only mutation, revisioning, audit, draft/publish/restore, survey diagnostics | operational dual-control if required |
| Event storm | nuisance/operational overload | quality gating, boundary hysteresis/debounce logic, source/status filters | site tuning under BT-14 acceptance |
| False multimodal association | wrong person/asset continuity | confidence/ambiguity thresholds, low-confidence tracks stay separate, provenance retained, no biometrics | quantify false-association rate under BT-15/BT-13 site scenarios |
| Supply-chain vulnerability | compromised image/SDK/dependency | SDK isolated behind adapter process, pinned CI actions, required vulnerability scans | release-block critical/high findings |
| Data remanence | excessive precise history retained | independent raw/tracked/telemetry retention and scheduled cleanup | align retention values with policy/legal basis |

## Security release rule

Any unresolved critical/high vulnerability in SceneScape Bluetooth code,
container images, Helm deployment, provider adapter or required vendor SDK is a
release blocker unless formally accepted by the applicable security
governance process.
