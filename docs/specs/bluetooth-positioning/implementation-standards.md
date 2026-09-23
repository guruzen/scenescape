# Implementation Standards / Definition of Done

## Before coding
1. Read feature.md, architecture.md, data-contracts.md, this file and target BT file.
2. Verify dependencies are COMPLETE.
3. Inspect current branch; specs do not override current code reality.
4. Record cross-cutting deviations in central docs plus active BT file.

## After coding
1. Unit tests.
2. API/integration tests.
3. Regression tests for touched SceneScape behavior.
4. Frontend typecheck/build/lint where relevant.
5. Security/input/auth tests.
6. Requested performance/accuracy evidence.
7. Evidence Markdown under .github/evidence/bluetooth-positioning/BT-xx-*.md.
8. Update BT status/checklists and implementation commit.
9. Commit message begins BT-xx:.

## Status
PLANNED, READY, IN_PROGRESS, BLOCKED, COMPLETE.

## Compatibility
With Bluetooth disabled, existing APIs/rendering/deployment work as before and no existing data is deleted.

## Data quality
UTC; preserve source+ingest timestamps; units explicit; unknown != zero; every position has provenance/quality/freshness; reject NaN/Infinity; algorithm versions recorded; predictions expire.

## Security
OIDC for browser, service auth for provider; server-side scene scope; person/history least privilege; mutations audited; MQTT ACL; secret/pairing material not returned; bounded input sizes; review new dependencies/images for vulnerabilities.

## UX
Source/freshness/uncertainty/status visible; color not sole status signal; keyboard accessible; degraded position never rendered as precise truth; diagnostics separated from normal operator flow.

## Algorithm evidence
Use deterministic simulator ground truth and report error distributions. “A coordinate exists” is not an acceptable solver test.

## Performance evidence
Record workload shape, tags, anchors, Hz, hardware/runtime, duration, drop rate and P50/P95/P99.

## COMPLETE means
Acceptance criteria pass; tests/evidence exist; no unresolved critical/high security issue; rollback/disable path understood; docs match implementation; commit recorded.
