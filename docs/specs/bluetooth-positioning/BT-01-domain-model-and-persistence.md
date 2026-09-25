# BT-01 — Domain Model and Persistence

**Status:** COMPLETE  
**Dependencies:** BT-00  
**Program:** SceneScape Bluetooth High-Accuracy Positioning

## Objective

Introduce stable anchor/tag/provider/assignment/calibration resources and migrations.

## User stories

- Admin persists anchors/tags with IDs+serials.
- Admin assigns a tag while retaining history.
- Installer stores scene-bound calibration.

## Scope / functional requirements

1. Validated anchor/tag/provider/assignment/calibration models.
2. Serial required; BLE address is mutable metadata.
3. Lifecycle + optimistic revision semantics.
4. Assignment validity intervals/history.
5. Non-destructive reversible migrations.
6. Unknown telemetry represented explicitly.

## Implementation design

- Reuse native Resource for low-rate config when suitable; otherwise justified tables.
- Domain services enforce invariants.
- Indexes for scene/state/serial/provider identity.
- High-rate tables deferred.

## API, data and events

- Internal services first; public API BT-02.

## UX / operational behavior

- No production UI; fixtures allowed.

## Security, privacy and failure handling

- Scene required for calibrated anchor.
- Assignments capture actor/audit.
- No secrets in resource payload.

## Required tests

- [x] Migration up/down empty+populated DB.
- [x] CRUD/invariant tests.
- [x] Revision conflict.
- [x] Assignment overlap/close.
- [x] Scene deletion/cascade policy.

## Evidence required

- [x] Migration/test output.
- [x] Serialized fixtures.

## Acceptance criteria

- [x] No existing data deleted.
- [x] Round-trip correct.
- [x] Migrations reversible.
- [x] Invariants enforced below route layer.

## Out of scope

- Public API/UI.
- Ranging.

## Rollback / disable strategy

Downgrade migration or disable feature resources.

## Implementation record

- Implementation commits: `a5ea92a16cec170487f61e5eca9c28fd27db1791`, `23b03b99e9d8e19438190f937279bdedd28d8f3b`
- Evidence: `.github/evidence/bluetooth-positioning/BT-01-domain-model-and-persistence.md`
- Known deviations: Dedicated relational tables are used instead of generic JSON resources because BT-01 requires portable uniqueness/indexing, assignment history, calibration revisions, and optimistic concurrency across SQLite/PostgreSQL.

## Continuation prompt

> Implement BT-01 from `docs/specs/bluetooth-positioning`. Read `feature.md`, `architecture.md`, `data-contracts.md`, `implementation-standards.md` and this file first. Verify dependencies and inspect the current branch. Implement only BT-01, add required unit/integration/regression tests and evidence, update this status/checklist/record, and commit with a message beginning `BT-01:`.
