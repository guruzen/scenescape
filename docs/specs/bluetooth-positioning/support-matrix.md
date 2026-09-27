# Bluetooth Positioning Support Matrix

This matrix distinguishes software capability from evidence-backed production
support. A row marked **Blocked** must not be converted into an accuracy or
hardware support claim until its listed evidence exists.

| Area                                             | Software state                       | Production support state                             | Evidence required                                                          |
| ------------------------------------------------ | ------------------------------------ | ---------------------------------------------------- | -------------------------------------------------------------------------- |
| Anchor/tag/provider control plane                | Implemented                          | Software-supported                                   | API/UI/integration/security gates                                          |
| Versioned anchor calibration                     | Implemented                          | Software-supported                                   | calibration persistence/rollback/E2E                                       |
| Deterministic simulator                          | Implemented                          | Test-only                                            | deterministic/fault-injection tests                                        |
| Normalized range ingestion                       | Implemented                          | Software-supported                                   | auth/replay/dedupe/backpressure tests                                      |
| Robust WLS 2D/2.5D/3D solver                     | Implemented                          | Software-supported for qualified inputs              | simulator accuracy/performance + later real-site qualification             |
| Kalman tracking/prediction                       | Implemented                          | Software-supported                                   | jitter/dropout/reset tests                                                 |
| Live/history/2D/3D projection                    | Implemented                          | Software-supported                                   | backend/UI/E2E regression                                                  |
| Battery/device telemetry                         | Implemented                          | Software-supported where provider exposes it         | standard/vendor normalization + freshness tests                            |
| Survey bias/GDOP/coverage                        | Implemented                          | Software-supported                                   | robust bias/coverage tests + UI/E2E                                        |
| Spatial incidents/health                         | Implemented                          | Software-supported                                   | quality/event-storm/filter tests                                           |
| BLE + vision fusion                              | Implemented, opt-in                  | Experimental until site-qualified                    | false-association/continuity evidence                                      |
| Vendor-neutral Channel Sounding adapter boundary | Implemented                          | Adapter framework only                               | concrete vendor HIL                                                        |
| Real Channel Sounding hardware stack             | No vendor-specific HIL in repository | **Blocked (BT-12)**                                  | hardware/firmware/SDK BOM, known-distance HIL, reconnect/capacity/security |
| P95 real-site accuracy claim                     | Qualification harness implemented    | **Blocked (BT-13)**                                  | static/dynamic LOS/NLOS/anchor-loss/repeatability/latency data             |
| BT-16 production release                         | Software hardening in progress       | **Blocked until BT-12/BT-13 and release scans pass** | full release-readiness evidence                                            |

## Accuracy wording

Until BT-13 real-site evidence exists, use:

> SceneScape implements a high-accuracy-capable Bluetooth positioning
> architecture with Channel Sounding as the preferred ranging provider.
> Production accuracy depends on the selected hardware, deployment geometry,
> environment and qualification evidence.

Do not claim the proposed 0.50 m / 1.00 m P95 targets as achieved.
