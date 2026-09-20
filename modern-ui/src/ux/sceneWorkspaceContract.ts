export const PRIMARY_MODES = ["Monitor", "Analyze", "Configure"] as const
export type ScenePrimaryMode = (typeof PRIMARY_MODES)[number]

export const SECONDARY_VIEWS_BY_MODE: Record<ScenePrimaryMode, readonly string[]> = {
  Monitor: ["2D Scene", "3D Scene", "Cameras", "Sensors"],
  Analyze: ["History", "Trends", "Runtime"],
  Configure: ["Scene", "Cameras", "Sensors", "Geometry", "Hierarchy", "Calibration"],
}

export const DEFAULT_VIEW_BY_MODE: Record<ScenePrimaryMode, string> = {
  Monitor: "2D Scene",
  Analyze: "History",
  Configure: "Geometry",
}

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

export const ROUTE_BY_DESTINATION_KEY: Record<string, string> = {
  "Configure:Scene": "scenes",
  "Configure:Cameras": "cameras",
  "Configure:Sensors": "sensors",
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

export function legacyTabForDestination(destination: SceneDestination): LegacySceneTab | null {
  const key = destinationKey(destination)
  const match = LEGACY_SCENE_TABS.find((tab) => destinationKey(SCENE_DESTINATION_BY_LEGACY_TAB[tab]) === key)
  return match ?? null
}

export function defaultDestinationForMode(mode: ScenePrimaryMode): SceneDestination {
  return { mode, view: DEFAULT_VIEW_BY_MODE[mode] }
}

export function routeForDestination(destination: SceneDestination): string | null {
  return ROUTE_BY_DESTINATION_KEY[destinationKey(destination)] ?? null
}
