# BT-00 — Architecture and Specification Baseline

**Status:** COMPLETE (planning baseline)  
**Dependencies:** None  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective
Establish the durable product definition, architecture, contracts, iteration boundaries and quality gates before runtime code.

## User stories
- Product owner sees complete decomposition and acceptance path.
- Engineer/AI can resume one BT item without chat history.
- Architecture decisions remain durable.

## Scope / functional requirements
1. Create central feature/architecture/contracts/standards docs.
2. Create BT-00..BT-16 specs.
3. Keep Channel Sounding preferred but core vendor-neutral.
4. Specify measurable accuracy, identity, privacy, security, retention, observability and rollback.

## Implementation design
- No product code.
- Treat specs as living documents; cross-cutting changes update central docs.

## API, data and events
- No runtime endpoints; data-contracts.md is the baseline.

## UX / operational behavior
- Document future management navigation and Live layers only.

## Security, privacy and failure handling
- Least privilege for person assignments/precise location.
- Provider service auth separated from browser OIDC.

## Required tests
- [ ] Validate all files/index.
- [ ] Review dependency graph for cycles.
- [ ] Confirm no hardware prerequisite before BT-12.

## Evidence required
- [ ] Specification commit SHA.
- [ ] Reference assumptions captured.

## Acceptance criteria
- [ ] All 22 planning files committed.
- [ ] Every BT item has tests/evidence/acceptance/rollback and resume prompt.
- [ ] A future session can act from BT ID.

## Out of scope
- Runtime implementation.
- Hardware purchase.

## Rollback / disable strategy
Revert this documentation commit.

## Implementation record
- Implementation commit: _not yet recorded_
- Evidence: _not yet recorded_
- Known deviations: _none at planning baseline_

## Continuation prompt
> Implement BT-00 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-00, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-00:`.
