/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

export const SCENE_LAYOUT_BREAKPOINTS = {
  drawer: 1100,
  narrow: 600,
} as const;

export const SCENE_VISUAL_HIERARCHY = [
  "status",
  "primary-navigation",
  "secondary-navigation",
  "view-controls",
  "visualization",
  "inspector",
] as const;

export const SUPPORTED_UI_THEMES = [
  { value: "light", label: "Spatial Light" },
  { value: "light-air", label: "Soft Light" },
  { value: "dark", label: "Spatial Dark" },
  { value: "dark-command", label: "Dense Dark" },
  { value: "liquid-glass", label: "Liquid Glass" },
] as const;

export type UiTheme = (typeof SUPPORTED_UI_THEMES)[number]["value"];
export type SceneLayoutMode = "desktop" | "drawer" | "narrow";

export function layoutModeForWidth(width: number): SceneLayoutMode {
  if (width <= SCENE_LAYOUT_BREAKPOINTS.narrow) return "narrow";
  if (width <= SCENE_LAYOUT_BREAKPOINTS.drawer) return "drawer";
  return "desktop";
}
