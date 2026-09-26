/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import type { SceneStatusModel } from "./sceneStatus";
import { LIVE_REGION_POLICY } from "./sceneAccessibility";

export default function SceneStatusHeader({
  sceneName,
  sceneId,
  status,
}: {
  sceneName: string;
  sceneId: string;
  status: SceneStatusModel;
}) {
  const stateClass =
    status.state === "LIVE"
      ? "live"
      : status.state === "DEGRADED"
        ? "degraded"
        : "stale";
  const cameraHealth =
    status.cameraHealthy === null
      ? `Unknown / ${status.cameraTotal}`
      : `${status.cameraHealthy} / ${status.cameraTotal}`;
  const sceneRate =
    status.sceneRate === null ? "Unknown" : `${status.sceneRate.toFixed(1)} Hz`;
  const age =
    status.ageSeconds === null
      ? "No retained observation"
      : `${status.ageSeconds.toFixed(1)}s ago`;

  return (
    <section
      className="scene-status-header"
      aria-label="Scene operational status"
    >
      <div className="scene-status-identity">
        <div>
          <span>Scene</span>
          <strong>{sceneName}</strong>
          <code>{sceneId}</code>
        </div>
        <span
          className={`scene-status-state ${stateClass}`}
          role="status"
          aria-live={LIVE_REGION_POLICY.sceneState}
          aria-atomic="true"
        >
          <i aria-hidden="true" />
          {status.state}
        </span>
      </div>
      <div className="scene-status-metrics">
        <div>
          <span>Objects</span>
          <b>{status.objectCount}</b>
        </div>
        <div>
          <span>Scene rate</span>
          <b>{sceneRate}</b>
        </div>
        <div>
          <span>Cameras</span>
          <b>{cameraHealth}</b>
        </div>
        <div>
          <span>MQTT</span>
          <b>{status.mqtt}</b>
        </div>
        <div>
          <span>Latest observation</span>
          <b>{age}</b>
        </div>
      </div>
    </section>
  );
}
