# BT-05 Evidence — Deterministic Positioning Simulator

## Status

**COMPLETE**

## Scope delivered

BT-05 provides a deterministic, truth-known Bluetooth positioning simulator for
development, QA and downstream positioning tests.

Delivered behavior:

- fixed anchors with optional deterministic range bias;
- moving tags with linearly interpolated 3D trajectories;
- ideal geometric range generation;
- Gaussian range noise;
- NLOS bias;
- outliers;
- packet loss;
- timestamp jitter;
- deterministic out-of-order delivery;
- anchor outage windows;
- batch, realtime and accelerated playback modes;
- synthetic battery percentage/status and last-seen timestamps;
- explicit schema/simulator version metadata;
- separate truth, measurement and telemetry collections;
- fail-closed runtime guard that refuses production use.

## Implementation commits

- `ee76196bb71ac385454041ebb7409b4f8e236c50` — deterministic simulator core.
- `5118f32c92abdd5b03286101ab54c3918f5f5a09` — deterministic simulator tests.
- `9576ce4dc5d69dcf9582a8e836daae5d75c5002b` — canonical simulator scenarios.
- `b675d2a9f50021d496fe944db3683c2b30a1e7a0` — Bluetooth CI gate coverage.
- `bdffbf09dc9986414015bb216622a18b1e083cd4` — explicit bias, jitter and playback-mode coverage.

Post-BT-05 compatibility adjustment:

- `6a607e01a78bcad994195781d8e12129fc946011` aligns the simulator range
  envelope exactly with the BT-06 transport-neutral ingest contract. It does
  not expose ground truth.

## Canonical scenarios

`control-api/tests/data/bluetooth-positioning/scenarios.json` contains:

1. `static-center` — static tag in four-anchor geometry.
2. `warehouse-walk-nlos` — moving tag with noise, NLOS, outliers, loss,
   jitter, out-of-order delivery and an anchor outage.
3. `forklift-edge` — moving asset trajectory exercising edge geometry.

Together these cover the planned static/walk/forklift/edge/NLOS/outage
scenario classes while keeping the scenario bundle compact and reproducible.

## Truth isolation

`simulate()` returns three independent collections:

- `measurements`
- `truth`
- `telemetry`

Normalized range envelopes contain only scene/anchor/tag identifiers and the
provider-style range payload. They do not contain truth coordinates or ideal
distance. Ground truth therefore cannot be consumed accidentally by BT-06 or
the solver through the normalized measurement contract.

Synthetic provenance is explicit:

- measurement `provider_details.synthetic=true`
- truth `synthetic=true`
- simulator version included in both paths

## Failure-mode evidence

The automated simulator tests cover:

- same seed produces identical measurements/truth/telemetry;
- exact zero-noise geometry;
- deterministic anchor bias;
- deterministic timestamp jitter;
- Gaussian noise configuration;
- forced NLOS;
- forced outliers;
- complete packet loss;
- anchor outage/recovery;
- deterministic out-of-order delivery;
- truth interpolation;
- battery drain and last-seen values;
- malformed/ambiguous scenario rejection;
- unknown outage-anchor rejection;
- realtime mode rejecting acceleration;
- accelerated playback scaling elapsed simulated time;
- production runtime refusal even when the enable flag is present.

## CI evidence

GitHub Actions run:

`https://github.com/guruzen/scenescape/actions/runs/36287293204`

The Python regression step executed all `control-api/tests/test_bluetooth_*.py`
tests.

Result:

```text
119 passed, 2 failed, 1 warning
```

The two failures are unrelated to BT-05:

1. `test_bt01_schema_downgrade_refuses_silent_bluetooth_data_loss`
   expected an older error-message string after later schema-hardening work.
2. `test_bt16_disabling_bluetooth_removes_live_overlay_without_deleting_history`
   has a missing `select` import in a BT-16 test.

No BT-05 simulator test failed. The BT-05 simulator suite therefore passed in
the aggregate run. The UI/build and Helm jobs in the same run also passed.

## Acceptance evidence

- [x] Same seed = same data.
- [x] Range bias/noise/NLOS/outlier/loss/jitter/out-of-order/outage are available.
- [x] Realtime and accelerated playback semantics are validated.
- [x] Ground truth is separated from normalized provider measurements.
- [x] Battery and last-seen simulation are present.
- [x] Canonical scenario bundle is versioned.
- [x] Synthetic data is visibly marked.
- [x] Simulator cannot be enabled accidentally in production.
- [x] Normalized measurements are compatible with the BT-06 contract.

## Known limitations / deferred items

- The simulator is intentionally test/development-only.
- It does not claim radio realism or certify Bluetooth accuracy.
- It does not emulate a specific vendor's Channel Sounding PHY/SDK behavior.
- Real hardware/provider behavior belongs to BT-12.
- Accuracy qualification belongs to BT-13.

## Rollback

The simulator is isolated from production runtime behavior. Removing
`bluetooth_simulator.py`, its scenario bundle and tests has no production
data migration or runtime side effect.
