# BT-08 Evidence — Tracking Engine

## Status

**COMPLETE**

## Scope delivered

BT-08 adds a bounded quality-aware constant-velocity Kalman tracker on top of
BT-07 raw solves.

Delivered behavior:

- one track per scene/tag;
- solver uncertainty converted into measurement covariance;
- smoothed x/y/z;
- vx/vy/vz velocity and optional heading;
- measured good/degraded states;
- bounded predicted state;
- stale state after prediction expiry;
- unavailable state after stale expiry;
- reset after calibration revision change;
- reset after tag assignment/identity revision change;
- reset after motion-class change;
- reset after long measured gaps;
- reset instead of smoothing physically impossible jumps;
- deterministic out-of-order rejection;
- LRU memory bound and eviction metrics;
- configurable per-tag-class motion limits;
- tracked-position persistence with solver/tracker/provenance fields.

## Implementation commits

Core implementation:

- `019b584f8c66` — tracked-position persistence.
- `311022ef40f8` — quality-aware constant-velocity tracker.
- `eef4e0f43f37` — tracked-position schema migration.
- `dd0da8afc576` — database lifecycle integration.
- `dc8940d13644` — state/jitter/velocity/reset tests.
- `92c5071729f7` — measurement → solve → track pipeline.
- `8ee126874dab` — worker queue drain integration.
- `7b0ced184d9d` — same-timestamp multi-anchor refinement.
- `92a34d7faacb` — safe tracker provenance serialization.

Completion work:

- `c08b1062652a` — long-gap, scene isolation and persistence evidence.
- `9e07cd592ba9` — focused BT-08 tracking gate.
- `276ef568625d` — tag-class motion limits.
- `09a81d076ea9` — assignment motion class routed into tracker.
- `70b70ef54174` — tag-class motion-limit tests.
- `5e277c060ccb` — assignment motion-class context test.
- `521060c401ed` — motion-limit environment parser test.
- `48f55495eac9` — final focused gate coverage.

## Jitter and position evidence

A seeded stationary sequence adds approximately 0.22 m Gaussian noise on both
horizontal axes. After tracker warm-up, the regression requires:

```text
mean tracked horizontal error < mean raw horizontal error
```

This directly verifies that temporal filtering reduces stationary jitter
instead of merely reproducing raw fixes.

## Velocity evidence

For a truth trajectory moving at 1.2 m/s in +x:

- final position error is < 0.2 m;
- `|vx - 1.2| < 0.15 m/s`;
- `|vy| < 0.1 m/s`;
- heading resolves within 5 degrees of +x.

The stop/start/turn regression also verifies:

- velocity decays below 0.25 m/s after stopping;
- a subsequent +y turn produces `vy > 0.4 m/s`;
- heading moves into the expected 45–135 degree sector.

## State timeline evidence

With:

- prediction horizon = 2 s;
- stale horizon = 4 s;

and the last measured fix at t=3 s:

| Event time | Output state | Behavior |
| --- | --- | --- |
| t=4 s | predicted | bounded constant-velocity prediction |
| t=6 s | stale | prediction retained but visibly stale |
| t=8 s | unavailable | coordinate removed and track expired |

Predicted output includes `tracker.predicted=true` and retains the last
measured timestamp and contributing anchor provenance.

## Reset/isolation evidence

Automated tests verify:

- an older out-of-order fix is ignored and cannot rewind the track;
- an impossible jump resets to the measured fix rather than smoothing a false
  path;
- calibration revision change resets the filter;
- assignment/identity revision change resets the filter;
- motion-class change resets the filter;
- a measured gap beyond `reset_gap_s` resets velocity/history;
- the same tag ID in two scenes creates independent tracks;
- smoothing never crosses scene or identity boundaries.

## Tag-class motion limits

BT-08 supports class-specific physical limits through:

```text
BLUETOOTH_TRACKER_MOTION_LIMITS_JSON
```

Example:

```json
{"person": 2.2, "vehicle": 12.0, "asset": 4.0}
```

An active tag assignment's `entity_type` becomes the motion class. Unknown or
invalid classes fall back to the configured global `max_speed_mps`.

The regression proves that the same 5 m one-second displacement is rejected as
an impossible jump for a 2 m/s person limit while remaining admissible under a
10 m/s vehicle limit.

## Memory and operational evidence

A 250-tag creation test with `max_tracks=100` verifies:

- only 100 tracks remain resident;
- 150 oldest tracks are evicted;
- an evicted tag restarts as a new track;
- eviction is observable through tracker metrics.

## Persistence evidence

The tracked-position persistence regression reloads a stored row and verifies:

- quality state and predicted flag;
- vx/vy/vz;
- positioning method;
- solver name/version;
- tracker name/version;
- calibration revision;
- identity revision;
- accepted anchor IDs;
- update/reset reason.

## Covariance handling

BT-07 v1 exposes horizontal/vertical uncertainty rather than a full covariance
matrix. BT-08 conservatively converts those 95%-style uncertainty values into
a diagonal measurement covariance for the Kalman update. The Joseph covariance
update is used to preserve numerical stability.

## CI evidence

Focused GitHub Actions run:

`https://github.com/guruzen/scenescape/actions/runs/36288300922`

The gate compiles the BT-08 tracker/pipeline modules and runs:

- all `test_bluetooth_tracking.py` tests;
- BT-08 raw→tracked pipeline integration;
- assignment motion-class context;
- motion-limit environment configuration;
- same-timestamp refinement regression.

Result:

```text
17 passed in 1.32s
```

## Acceptance evidence

- [x] Constant velocity converges deterministically.
- [x] Stop/start/turn behavior updates velocity and heading.
- [x] Raw jitter is reduced after warm-up.
- [x] Prediction expires to stale then unavailable.
- [x] Out-of-order data cannot rewind state.
- [x] Impossible jumps reset rather than create false paths.
- [x] Calibration, identity, motion-class and long-gap resets are enforced.
- [x] Same tag ID is isolated by scene.
- [x] Per-tag-class motion limits are configurable.
- [x] Large tag count is memory bounded.
- [x] Tracked position provenance persists.
- [x] Raw→solve→track integration is tested.

## Known limitations / deferred items

- BT-07 exposes uncertainty scalars, not a full solver covariance matrix;
  BT-08 derives a conservative diagonal measurement covariance from those
  uncertainty values.
- Prediction is deliberately short-lived and is not dead reckoning for long
  outages.
- Vision fusion belongs to BT-15.
- Rendering predicted/stale states belongs to BT-09.

## Rollback

Disable the tracker and consume BT-07 raw solves directly. Tracked history is
additive and can remain stored for diagnostics.
