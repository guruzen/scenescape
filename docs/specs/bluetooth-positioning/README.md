# SceneScape Bluetooth High-Accuracy Positioning (BHAP)

This folder is the durable Spec Kit-style source of truth for Bluetooth positioning in SceneScape.

## Resume protocol

A future session can say:

> Implement BT-04 from docs/specs/bluetooth-positioning. Read feature.md, architecture.md, data-contracts.md, implementation-standards.md and BT-04 first. Verify dependencies, implement only that iteration, add tests/evidence, update status/checklists, and commit.

## Direction

- Fixed Bluetooth devices are **anchors/locators**; moving devices are **tags**.
- Bluetooth Core 6.x Channel Sounding is the preferred high-accuracy provider.
- AoA/Direction Finding is an alternate high-accuracy provider; RSSI is fallback/proximity.
- Hardware SDKs terminate at provider adapters; SceneScape core contracts remain vendor-neutral.
- Every position carries source, timestamp, freshness, uncertainty and quality. No false precision.
- Simulator-first development makes BT-01..BT-11 hardware-independent.
- BLE addresses are transport metadata, not permanent identity.
- Real accuracy claims are owned by BT-13 qualification evidence.

## Iterations

| ID    | Feature                             | Dependencies        |
| ----- | ----------------------------------- | ------------------- |
| BT-00 | Architecture/specification baseline | none                |
| BT-01 | Domain model and persistence        | BT-00               |
| BT-02 | Control-plane API                   | BT-01               |
| BT-03 | Management UI                       | BT-02               |
| BT-04 | Scene anchor calibration            | BT-02, BT-03        |
| BT-05 | Positioning simulator               | BT-04               |
| BT-06 | Measurement ingestion               | BT-01, BT-05        |
| BT-07 | Positioning engine v1               | BT-04, BT-06        |
| BT-08 | Tracking engine                     | BT-07               |
| BT-09 | Scene data-plane integration        | BT-08               |
| BT-10 | Device/battery telemetry            | BT-02, BT-06        |
| BT-11 | Advanced calibration and coverage   | BT-07               |
| BT-12 | Real Channel Sounding provider      | BT-06, BT-10, BT-11 |
| BT-13 | Accuracy qualification              | BT-12               |
| BT-14 | Operational integration             | BT-09, BT-10        |
| BT-15 | Multimodal BLE + vision fusion      | BT-09, BT-13        |
| BT-16 | Production hardening/release        | BT-13, BT-14, BT-15 |

## Program files

- feature.md — product/user requirements.
- architecture.md — subsystem architecture, algorithms, security/deployment/failure model.
- data-contracts.md — canonical resources, MQTT and API shapes.
- implementation-standards.md — test/evidence/quality Definition of Done.
- BT-00..BT-16 — independently resumable implementation specs.

## Program principles

1. No naked coordinates: provenance and uncertainty are mandatory.
2. Poor geometry or stale measurements degrade visibly.
3. Vendor-neutral core and replaceable provider adapters.
4. Stable SceneScape identity is independent of BLE address.
5. 2D/2.5D is preferred over invented z precision.
6. Person/tag assignment and exact history are privacy-sensitive.
7. Feature disabled means existing SceneScape behavior is unchanged.
8. Each BT iteration ends with tests, evidence, checklist update and a commit.
