# BT-12 Evidence — Real Channel Sounding Provider

## Status

**BLOCKED — REAL HARDWARE / VENDOR HIL REQUIRED**

BT-12 is not complete. SceneScape's vendor-neutral provider boundary is
implemented and software-qualified, but the repository contains no concrete
vendor Channel Sounding adapter or hardware-in-the-loop evidence.

This file intentionally separates **software readiness** from **real hardware
qualification** so FakeProvider/simulator evidence cannot be mistaken for a
production hardware claim.

## Software readiness delivered

The BT-12 framework currently provides:

- vendor-neutral `RangingProvider` abstraction;
- SDK-isolated JSON-lines subprocess adapter boundary;
- provider capability declaration:
  - hardware;
  - firmware;
  - SDK;
  - methods;
  - maximum concurrent sessions;
  - maximum update rate;
  - provider diagnostics;
- initiator / reflector / auto role configuration contract;
- Channel Sounding session start/stop contract;
- provider ID binding;
- normalized measurement mapping into the unchanged BT-06 `RangeEnvelope`;
- provider diagnostic preservation, including PBR/RTT-style fields when
  supplied by an adapter;
- normalized telemetry mapping into the unchanged BT-10 device telemetry
  contract;
- capacity-aware priority scheduler;
- queued/active/available session diagnostics;
- sample/failure/reconnect counters;
- reconnect/requeue behavior;
- bounded exponential reconnect backoff;
- deployment-mounted provider secrets file rather than browser/API payload
  secrets.

## Implementation commits

- `3f7028167350` — vendor-neutral ranging provider boundary.
- `ee2b56c63840` — provider scheduling and reconnect contract tests.
- `0a822f95f10d` — focused BT-12 software-readiness gate.

## Software CI evidence

Focused GitHub Actions run:

`https://github.com/guruzen/scenescape/actions/runs/36292521817`

Provider contract tests:

```text
6 passed in 0.29s
```

Simulator non-regression:

```text
14 passed in 0.10s
```

This proves the adapter boundary remains compatible with the normalized core
contracts and that adding the provider framework does not break the BT-05
simulator.

It does **not** prove a real Channel Sounding stack works.

## What the software tests prove

### Core contract preservation

A provider measurement is normalized into the existing BT-06 range contract
with:

- SceneScape scene/anchor/tag IDs;
- `method=channel_sounding`;
- provider/session/sequence/timestamp/range/quality data;
- hardware/firmware/SDK/adapter provenance;
- bounded provider diagnostics.

No vendor SDK type is introduced into the solver, tracker or scene contracts.

### Telemetry preservation

Provider telemetry maps into the BT-10 normalized telemetry contract while
retaining firmware and bounded provider details.

### Scheduler/capacity behavior

The FakeProvider regression configures two concurrent sessions and submits four
tags. It proves:

- two active sessions;
- two queued sessions;
- zero currently available slots;
- explicit `capacity_limited` accounting;
- queued work starts when an active session is cancelled.

This proves scheduler logic only. It does not establish the capacity of any
real vendor controller/radio.

### Recovery contract

The software regression proves:

- active session activity/sample timestamps are recorded;
- reconnect causes active/queued requests to be resubmitted;
- reconnect count is exposed;
- exponential retry is bounded;
- final connection failure propagates.

This is process-level contract evidence, not device/gateway reboot HIL.

## Existing release-blocking statement

`docs/specs/bluetooth-positioning/support-matrix.md` already states:

- vendor-neutral Channel Sounding adapter boundary: implemented / adapter
  framework only;
- real Channel Sounding hardware stack: **Blocked (BT-12)**;
- required evidence: hardware/firmware/SDK BOM, known-distance HIL,
  reconnect/capacity/security.

The Bluetooth threat model also leaves real provider identity/ACL behavior,
vendor sequence/session semantics, vendor SDK logging and gateway hardening as
BT-12 HIL actions.

## Missing evidence — blocker

The following required BT-12 evidence does **not** exist in the repository:

1. a selected real Channel Sounding vendor/hardware stack;
2. concrete hardware model/part numbers;
3. tested firmware revision(s);
4. tested vendor SDK/package revision and license;
5. concrete adapter executable/container implementing the JSON-lines boundary;
6. real initiator/reflector provisioning evidence;
7. hardware-in-the-loop smoke output;
8. known-distance real range samples;
9. real multi-tag scheduling/capacity measurements;
10. real update-rate measurements;
11. gateway/device reboot and reconnect recovery evidence;
12. real battery/device telemetry evidence;
13. PBR/RTT/quality diagnostic mapping evidence where supported;
14. end-to-end real measurements persisted by BT-06 and solved/tracked by
    BT-07/BT-08;
15. vendor adapter/SDK dependency and vulnerability scan;
16. provider service identity / MQTT ACL / secret-log review on the concrete
    deployment.

## HIL completion plan

Once hardware is available, finish BT-12 in this order.

### HIL-01 — Freeze BOM

Record:

- vendor;
- anchor/initiator model and part number;
- tag/reflector model and part number;
- gateway/controller if used;
- firmware for every component;
- SDK/API package and exact version;
- host OS/architecture;
- adapter build/container digest;
- vendor license/dependency inventory.

### HIL-02 — Concrete adapter

Implement the vendor-specific process behind `JsonLineRangingProvider`.

It must support at minimum:

- `health`;
- `configure_role`;
- `start_session`;
- `stop_session`;
- `poll`.

Vendor SDK objects stay inside the adapter process.

### HIL-03 — Known-distance smoke

Use measured reference separations, preferably including at least:

- short LOS;
- medium LOS;
- longer LOS within the supported environment.

For every sample retain:

- truth/reference distance;
- reported range;
- source timestamp;
- method;
- quality;
- PBR/RTT diagnostics if available;
- firmware/SDK/adapter version.

BT-12 only requires sanity and transport correctness; statistical site accuracy
acceptance belongs to BT-13.

### HIL-04 — Capacity / update-rate test

Exercise:

- one tag;
- increasing concurrent tags up to vendor capacity;
- one request beyond capacity;
- requested vs achieved update rate;
- queued/active/capacity-limited diagnostics;
- fairness when a slot becomes available.

### HIL-05 — Recovery

While ranging:

- restart adapter process;
- restart gateway/controller;
- reboot or disconnect/reconnect one ranging device where practical.

Verify:

- no fabricated coordinates;
- sessions recover or become explicitly unavailable;
- reconnect/failure counters move;
- solver/tracker resume on valid new measurements.

### HIL-06 — Telemetry

Verify real provider/device telemetry maps to BT-10 with:

- source;
- observed timestamp;
- battery if exposed;
- firmware/device information if exposed;
- unknown rather than fabricated values when absent.

### HIL-07 — End-to-end data path

Prove a real range travels:

```text
real radio / vendor SDK
  -> vendor adapter
  -> normalized BT-06 measurement
  -> persisted raw range
  -> BT-07 raw solve
  -> BT-08 tracked position
  -> BT-09 live/history
```

### HIL-08 — Security / supply chain

Capture:

- SDK dependency/license inventory;
- vulnerability scan of adapter/container/dependencies;
- service identity scope;
- MQTT/API ACL evidence if used;
- mounted secret mechanism;
- log inspection proving pairing/API secrets are not emitted.

Any unresolved critical/high vulnerability remains a release blocker.

## Required tests status

- [ ] HIL smoke — **blocked: no real hardware/vendor adapter**.
- [ ] Multi-tag scheduling — software scheduler tested; real capacity HIL
  still required.
- [ ] Reconnect/reboot — process contract tested; real gateway/device reboot
  HIL still required.
- [ ] Known-distance sanity — **blocked: no real hardware**.
- [ ] Telemetry — normalization tested; real-device telemetry HIL still
  required.
- [ ] Capacity saturation — software capacity logic tested; real saturation
  HIL still required.
- [x] Simulator regression — 14 tests passed in focused BT-12 gate.

## Acceptance status

- [ ] Real measurements flow through solver/tracker.
- [x] Core contracts remain vendor-neutral and unchanged.
- [ ] Real hardware recovery is demonstrated.
- [ ] Real provider capacity is measured and visible.

## Hardware/accuracy claim guardrail

Do not say that SceneScape currently supports a specific Channel Sounding
hardware stack based on this framework.

Do not claim the proposed 0.50 m / 1.00 m P95 targets as achieved.

Permitted wording remains:

> SceneScape implements a high-accuracy-capable Bluetooth positioning
> architecture with Channel Sounding as the preferred ranging provider.
> Production accuracy depends on the selected hardware, deployment geometry,
> environment and qualification evidence.

## Rollback

The provider deployment is optional. Disable/remove the concrete provider
adapter and its service configuration; BT-05 simulator, BT-06 normalized
ingestion, solver, tracker and existing scene data plane remain available.
