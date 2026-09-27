# BT-10 Evidence — Device and Battery Telemetry

## Status

**COMPLETE**

## Scope delivered

BT-10 adds trustworthy, provenance-bearing Bluetooth device telemetry without
making telemetry availability a commissioning prerequisite.

Delivered behavior:

- Bluetooth Battery Service normalization;
- Device Information Service normalization;
- vendor-adapter normalization;
- provider device-envelope normalization;
- manual/stable inventory fallback when optional services are absent;
- source and observed/ingested timestamps;
- configurable low/critical battery thresholds;
- explicit unknown vs measured 0% semantics;
- stale/fresh telemetry semantics;
- service-authenticated writes;
- scene/admin-scoped reads;
- secret-field rejection;
- bounded LRU polling/cache guard;
- UI display of battery status, freshness, source, firmware/model and last seen.

## Implementation commits

Backend:

- `d44e3b5bfcf7` — normalized Bluetooth device telemetry.
- `025b517c555e` — provider device-envelope normalization.
- `826c56895336` — service telemetry ingest and read summaries.
- `6b4afcf1853d` — telemetry normalization/permission tests.
- `2a1932bb7c75` — telemetry scene fixture correction.
- `7d4652519f7d` — SQLite timestamp portability.

UI completion:

- `55e9cc76452e` — device telemetry read client.
- `17b32b2a47ac` — telemetry freshness/provenance/firmware presentation.
- `e273f76873d3` — telemetry Playwright screenshot evidence.
- `871bddd47954` — focused BT-10 backend/UI gate.

## Normalized samples

### Standard Bluetooth services

Input can contain Battery Service and Device Information Service values:

```text
battery_level: 73
battery_voltage_v: 3.1
manufacturer_name: Example
model_number: CS-Tag
hardware_revision: A
firmware_revision: 1.2.3
```

Normalized provenance:

```text
source: bluetooth_standard_services
battery_percent: 73
battery_voltage_v: 3.1
manufacturer: Example
model: CS-Tag
hardware_revision: A
firmware_revision: 1.2.3
```

Both optional services may be absent. In that case the normalized battery is
`null/unknown`; commissioning remains valid.

### Vendor adapter

A vendor payload can map vendor-specific fields such as `soc` and `volts`
to the common battery fields while retaining bounded non-secret extras in
`details`.

## Unknown / zero / stale semantics

BT-10 explicitly distinguishes:

- no battery report -> `unknown`;
- measured 0% -> `critical`;
- stale telemetry -> last measured value retained with `freshness.stale=true`;
- stale does not rewrite the battery value to zero or unknown.

Default thresholds are configurable through:

- `BLUETOOTH_BATTERY_CRITICAL_PERCENT` (default 10);
- `BLUETOOTH_BATTERY_LOW_PERCENT` (default 20);
- `BLUETOOTH_TELEMETRY_STALE_S` (default 3600 seconds).

Tests also verify alternate threshold settings.

## Stable manual / QR-derived fallback

Manufacturer, model, hardware revision and firmware revision remain stable
BT-01 device inventory fields and can be entered in the management UI when a
device does not expose the standard Device Information Service.

Externally decoded QR/inventory data can populate the same stable fields; BT-10
does not require a browser camera scanner or browser BLE pairing path. Missing
Battery/Device Information services therefore never block commissioning.

## Security evidence

Telemetry writes use service identity rather than browser identity.

Tests verify:

- browser tokens cannot write provider telemetry;
- service identity can write only matching provider data;
- tag telemetry reads are administrator restricted;
- anchor telemetry reads are scene scoped;
- telemetry `details` reject secret-like fields including password, token,
  pairing key, PIN, private key and PSK;
- provider details are size bounded;
- no pairing secret is stored in normalized telemetry.

## Polling/cache evidence

`TelemetryPollCache` provides:

- minimum per-device poll interval;
- thread-safe access;
- bounded LRU entries;
- deterministic eviction.

This protects battery-powered tags from aggressive telemetry polling and
prevents unbounded in-memory device state.

## UI evidence

The management UI now reads the dedicated telemetry endpoint for a selected
tag/anchor.

It displays:

- battery percentage plus low/critical/normal state;
- fresh/stale observed timestamp;
- telemetry source;
- firmware revision;
- model;
- last seen;
- explicit unknown state when no telemetry exists.

The UI explicitly notes that provider/gateway telemetry is used rather than
browser BLE pairing.

## CI evidence

Focused GitHub Actions run:

`https://github.com/guruzen/scenescape/actions/runs/36292150518`

Backend:

```text
10 passed, 1 warning in 2.04s
```

UI Playwright:

```text
1 passed (3.3s)
```

Scenario:

`BT-10 device telemetry shows battery freshness provenance and firmware`

The same UI job also passed TypeScript typecheck and production build.

## Screenshot artifact

Generated screenshot:

- `bt10-device-telemetry.png`

GitHub Actions artifact:

- name: `bt10-telemetry-ui-evidence`
- artifact ID: `10922393107`
- size: 152,193 bytes
- SHA-256: `b5bfb6911e5955efe101d7d0edf6d717ed60862a16420f0a95c738fc8409634d`
- expires: 2026-10-27

## Acceptance evidence

- [x] Standard service fixtures.
- [x] Vendor fixture.
- [x] Unknown/stale/0% distinction.
- [x] Configurable thresholds.
- [x] Permissions/security.
- [x] Bounded cache/polling.
- [x] UI screenshot.
- [x] Normalized samples.
- [x] Automated tests.
- [x] Battery has provenance and freshness.
- [x] Missing standard services do not block commissioning.
- [x] Low/critical battery states work.
- [x] No pairing secrets are stored.

## Known limitations / deferred items

- No firmware OTA is implemented.
- No browser BLE pairing is used.
- BT-10 does not implement an in-browser QR camera scanner; manual or
  externally decoded QR inventory values use the same stable device fields.
- Telemetry collection cadence is provider/gateway owned and guarded by the
  bounded poll cache.

## Rollback

Disable provider telemetry collection/ingest. Previously stored telemetry
naturally becomes stale while stable commissioned device configuration remains.
