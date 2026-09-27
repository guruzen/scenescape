# BT-00 Evidence — Architecture and Specification Baseline

## Status

**COMPLETE**

## Baseline

- Initial specification commit: `de56275646e1`
- Follow-up automated formatting commit: `4cb72ab9919f`
- Branch: `feature/react-keycloak-modern-ui`

## Delivered

- `docs/specs/bluetooth-positioning/README.md`
- `feature.md`
- `architecture.md`
- `data-contracts.md`
- `implementation-standards.md`
- Individually resumable `BT-00` through `BT-16` specifications.

## Verification

Repository contents were read back from GitHub after the baseline commit and all 22 Markdown files were present on the target branch.

## Decisions captured

- Channel Sounding preferred for high-accuracy ranging; AoA alternate; RSSI fallback.
- Vendor-neutral provider boundary.
- Stable anchor/tag identity independent of BLE address.
- Simulator-first program.
- Quality/freshness/uncertainty mandatory with every position.
- Measured accuracy qualification deferred to BT-13.
- Evidence/test/rollback gates defined per iteration.

## Acceptance

- [x] Central feature, architecture, contract and implementation-standard documents exist.
- [x] BT-01 through BT-16 each contain implementation/test/evidence/acceptance/rollback sections.
- [x] Each BT file contains a continuation prompt.
- [x] The implementation program can be resumed by BT identifier without relying on chat history.
