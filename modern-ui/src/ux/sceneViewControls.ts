export type SceneRenderer = "2d" | "3d";

export const COMMON_LAYER_CONTROLS = [
  "objects",
  "trails",
  "heatmap",
  "velocity",
  "spatial",
] as const;
export const DIAGNOSTIC_CONTROLS = ["telemetry"] as const;
export const RENDERER_CONTROLS: Record<SceneRenderer, readonly string[]> = {
  "2d": ["labels"],
  "3d": [
    "floor",
    "camera-frames",
    "camera-opacity",
    "camera-selection",
    "camera-view",
    "lighting",
  ],
};

export function controlsForRenderer(renderer: SceneRenderer): string[] {
  return [
    ...COMMON_LAYER_CONTROLS,
    ...DIAGNOSTIC_CONTROLS,
    ...RENDERER_CONTROLS[renderer],
  ];
}

export function summarizeLiveObjectAvailability(
  objects: Array<Record<string, unknown>> | null | undefined,
) {
  const rows = Array.isArray(objects) ? objects : [];
  const velocityVectors = rows.filter((object) => {
    const velocity = object.velocity;
    return (
      Array.isArray(velocity) &&
      velocity.length >= 2 &&
      velocity.slice(0, 2).every((value) => Number.isFinite(Number(value)))
    );
  }).length;
  return {
    total: rows.length,
    velocityVectors,
    trailsAvailable: rows.length > 0,
    heatmapAvailable: rows.length > 0,
    velocityAvailable: velocityVectors > 0,
  };
}
