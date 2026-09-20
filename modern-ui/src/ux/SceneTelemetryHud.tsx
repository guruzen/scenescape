/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import { deriveSceneTelemetry } from "./sceneTelemetry";
import { LIVE_REGION_POLICY } from "./sceneAccessibility";

type Row = Record<string, any>;

export default function SceneTelemetryHud({ live }: { live: Row }) {
  const telemetry = deriveSceneTelemetry(live);
  const sceneRate =
    telemetry.sceneRate === null
      ? "Unknown"
      : `${telemetry.sceneRate.toFixed(1)} Hz`;
  const age =
    telemetry.ageSeconds === null
      ? "Unknown"
      : `${telemetry.ageSeconds.toFixed(1)} s`;

  return (
    <aside
      className="scene-telemetry-hud"
      aria-label="Live scene telemetry"
      aria-live={LIVE_REGION_POLICY.telemetryMetrics}
    >
      <div className="scene-telemetry-title-row">
        <b>Live telemetry</b>
        <span
          className={
            telemetry.freshness === "Receiving"
              ? "ok-text"
              : telemetry.freshness === "Stale"
                ? "warning-text"
                : ""
          }
        >
          {telemetry.freshness}
        </span>
      </div>
      <div className="scene-telemetry-row">
        <span>Scene rate</span>
        <strong>{sceneRate}</strong>
      </div>
      <div className="scene-telemetry-row">
        <span>Objects</span>
        <strong>{telemetry.objectCount}</strong>
      </div>
      <div className="scene-telemetry-row">
        <span>Observation age</span>
        <strong>{age}</strong>
      </div>
      <div className="scene-telemetry-camera-list">
        <span>Camera FPS</span>
        {telemetry.cameraRates.length ? (
          telemetry.cameraRates.map(({ camera, fps }) => (
            <div key={camera}>
              <code>{camera}</code>
              <strong>{fps.toFixed(1)}</strong>
            </div>
          ))
        ) : (
          <em>Unknown</em>
        )}
      </div>
    </aside>
  );
}
