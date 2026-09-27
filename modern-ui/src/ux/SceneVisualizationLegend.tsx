/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

import { HEATMAP_RANGES } from "./sceneVisualization";

export default function SceneVisualizationLegend({
  showHeatmap,
  showVelocity,
  heatmapOpacity,
  velocityVectors,
  objectCount,
}: {
  showHeatmap: boolean;
  showVelocity: boolean;
  heatmapOpacity: number;
  velocityVectors: number;
  objectCount: number;
}) {
  if (!showHeatmap && !showVelocity) return null;

  return (
    <aside
      className="scene-visualization-legend"
      aria-label="Visualization legend"
    >
      {showHeatmap && (
        <section>
          <div className="scene-legend-title">
            <b>Heatmap</b>
            <span>{HEATMAP_RANGES[0]}</span>
          </div>
          <div className="scene-heat-scale" aria-hidden="true" />
          <div className="scene-heat-scale-labels">
            <span>Lower intensity</span>
            <span>Higher intensity</span>
          </div>
          <small>
            {objectCount} current tracked positions ·{" "}
            {Math.round(heatmapOpacity * 100)}% opacity
          </small>
        </section>
      )}
      {showVelocity && (
        <section>
          <div className="scene-legend-title">
            <b>Velocity</b>
            <span>
              {velocityVectors}/{objectCount} vectors
            </span>
          </div>
          <div className="scene-velocity-key">
            <i aria-hidden="true">→</i>
            <span>Direction; arrow length is bounded for readability</span>
          </div>
          {!velocityVectors && objectCount > 0 && (
            <small>No current objects report a usable velocity vector.</small>
          )}
        </section>
      )}
    </aside>
  );
}
