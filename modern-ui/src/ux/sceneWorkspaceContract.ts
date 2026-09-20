export const PRIMARY_MODES = ["Monitor", "Analyze", "Configure"] as const
export type ScenePrimaryMode = (typeof PRIMARY_MODES)[number]

export const LEGACY_SCENE_TABS = [
  "Live 2D",
  "Live 3D",
  "Camera feeds",
  "Sensors & telemetry",
  "Geometry",
  "Hierarchy",
  "Camera calibration",
  "Runtime",
  "History & replay",
  "Trends & analytics",
] as const

export type LegacySceneTab = (typeof LEGACY_SCENE_TABS)[number]

export type SceneDestination = {
  mode: ScenePrimaryMode
  view: string
}

export const SCENE_DESTINATION_BY_LEGACY_TAB: Record<LegacySceneTab, SceneDestination> = {
  "Live 2D": { mode: "Monitor", view: "2D Scene" },
  "Live 3D": { mode: "Monitor", view: "3D Scene" },
  "Camera feeds": { mode: "Monitor", view: "Cameras" },
  "Sensors & telemetry": { mode: "Monitor", view: "Sensors" },
  Geometry: { mode: "Configure", view: "Geometry" },
  Hierarchy: { mode: "Configure", view: "Hierarchy" },
  "Camera calibration": { mode: "Configure", view: "Calibration" },
  Runtime: { mode: "Analyze", view: "Runtime" },
  "History & replay": { mode: "Analyze", view: "History" },
  "Trends & analytics": { mode: "Analyze", view: "Trends" },
}

export const DEFAULT_SCENE_DESTINATION: SceneDestination = {
  mode: "Monitor",
  view: "2D Scene",
}

export const SCENE_WORKSPACE_CAPABILITIES = [
  "live-2d",
  "live-3d",
  "camera-feeds",
  "sensor-telemetry",
  "geometry-editor",
  "hierarchy-editor",
  "camera-calibration",
  "runtime-status",
  "history-replay",
  "trends-analytics",
  "trails",
  "telemetry",
  "heatmap",
  "velocity",
  "roi-visualization",
  "fullscreen",
] as const

export function destinationForLegacyTab(tab: string): SceneDestination | null {
  return (SCENE_DESTINATION_BY_LEGACY_TAB as Record<string, SceneDestination>)[tab] ?? null
}

export function destinationKey(destination: SceneDestination): string {
  return `${destination.mode}:${destination.view}`
}
