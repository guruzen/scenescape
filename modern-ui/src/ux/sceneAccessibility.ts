/* SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */

export const LIVE_REGION_POLICY = {
  sceneState: "polite",
  telemetryMetrics: "off",
} as const;

export function isSelectionActivationKey(key: string): boolean {
  return key === "Enter" || key === " ";
}

export function selectionAriaLabel(kind: string, name: string): string {
  const normalizedKind = kind === "object" ? "tracked object" : kind;
  const value = String(name || "").trim();
  return value
    ? `Inspect ${normalizedKind} ${value}`
    : `Inspect ${normalizedKind}`;
}
