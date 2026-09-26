// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "../api/client";

export type BluetoothPage<T> = {
  items: T[];
  total: number;
  offset: number;
  limit: number;
};

export type BluetoothAnchor = {
  uid: string;
  serial_number: string;
  scene_id?: string | null;
  provider_id?: string | null;
  provider_device_id?: string | null;
  bluetooth_address?: string | null;
  manufacturer?: string | null;
  model?: string | null;
  hardware_revision?: string | null;
  firmware_revision?: string | null;
  state: string;
  capabilities: string[];
  revision: number;
};

export type BluetoothTag = {
  uid: string;
  serial_number: string;
  provider_id?: string | null;
  provider_device_id?: string | null;
  bluetooth_address?: string | null;
  manufacturer?: string | null;
  model?: string | null;
  hardware_revision?: string | null;
  firmware_revision?: string | null;
  state: string;
  capabilities: string[];
  last_seen_at?: string | null;
  battery: {
    percent?: number | null;
    voltage_v?: number | null;
    status?: string | null;
    source?: string | null;
    observed_at?: string | null;
  };
  revision: number;
};

export type BluetoothAssignment = {
  uid: string;
  tag_uid: string;
  entity_type: string;
  entity_id: string;
  display_name?: string | null;
  valid_from: string;
  valid_to?: string | null;
  reason?: string | null;
  created_by: string;
  closed_by?: string | null;
  revision: number;
};

export type BluetoothCalibration = {
  uid: string;
  anchor_uid: string;
  scene_id: string;
  calibration_revision: number;
  state: "draft" | "active" | "retired";
  position: { x_m: number; y_m: number; z_m: number };
  orientation: { yaw_deg: number; pitch_deg: number; roll_deg: number };
  z_source: "measured" | "default" | "surveyed";
  details: Record<string, unknown>;
  coordinate_frame: string;
  parent_projection?: {
    parent_scene_id: string;
    position: { x_m: number; y_m: number; z_m: number };
    transform: {
      translation: number[];
      rotation: number[];
      scale: number[];
    };
  } | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  revision: number;
};

export type BluetoothGeometryWarning = {
  code: string;
  severity: "error" | "warning";
  anchor_uids: string[];
  message: string;
  distance_m?: number;
  spread_ratio?: number;
};

export type BluetoothGeometry = {
  scene_id: string;
  anchor_count: number;
  basis: string;
  max_span_m: number;
  spread_ratio: number;
  warnings: BluetoothGeometryWarning[];
  ready_for_2d: boolean;
};

export type BluetoothSurveyBias = {
  anchor_id: string;
  status: string;
  sample_count: number;
  accepted_count: number;
  rejected_count: number;
  bias_m?: number | null;
  stddev_m?: number | null;
  median_m?: number | null;
  mad_m?: number | null;
  calibration_uid?: string;
  calibration_revision?: number;
  points?: Array<{
    survey_point_uid: string;
    sample_count: number;
    median_residual_m: number;
  }>;
};

export type BluetoothCoverage = {
  scene_id: string;
  theoretical_geometry: {
    model: string;
    fixed_z_m: number;
    anchor_count: number;
    cells: Array<{
      x_m: number;
      y_m: number;
      gdop?: number | null;
      geometry_state: "good" | "degraded" | "poor" | "unavailable";
    }>;
  };
  observed_rf: {
    source: string;
    points: Array<{
      survey_point_uid: string;
      name: string;
      position: number[];
      sample_count: number;
      average_quality?: number | null;
    }>;
  };
};

export type BluetoothSurveyPoint = {
  uid: string;
  scene_id: string;
  name: string;
  position: { x_m: number; y_m: number; z_m: number };
  state: string;
};

export type CalibrationPayload = {
  anchor_uid: string;
  scene_id: string;
  x_m: number;
  y_m: number;
  z_m: number;
  yaw_deg: number;
  pitch_deg: number;
  roll_deg: number;
  z_source: "measured" | "default" | "surveyed";
  details?: Record<string, unknown>;
};

export type BluetoothDiagnostics = {
  anchors: {
    total: number;
    by_state: Record<string, number>;
    unassigned_scene: number;
  };
  tags: {
    visible: boolean;
    total?: number;
    by_state?: Record<string, number>;
    battery?: Record<string, number>;
  };
  scope: {
    all_scenes: boolean;
    scenes: string[];
  };
};

export type AnchorPayload = {
  uid?: string;
  serial_number: string;
  scene_id?: string;
  provider_id?: string;
  provider_device_id?: string;
  bluetooth_address?: string;
  manufacturer?: string;
  model?: string;
  hardware_revision?: string;
  firmware_revision?: string;
  capabilities: string[];
};

export type TagPayload = {
  uid?: string;
  serial_number: string;
  provider_id?: string;
  provider_device_id?: string;
  bluetooth_address?: string;
  manufacturer?: string;
  model?: string;
  hardware_revision?: string;
  firmware_revision?: string;
  capabilities: string[];
};

export type AssignmentPayload = {
  uid?: string;
  tag_uid: string;
  entity_type: string;
  entity_id: string;
  display_name?: string;
  reason?: string;
};

const query = (values: Record<string, string | number | undefined>) => {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
};

export const bluetoothApi = {
  anchors: {
    list(
      filters: {
        sceneId?: string;
        state?: string;
        serial?: string;
        providerId?: string;
        offset?: number;
        limit?: number;
      } = {},
    ) {
      return apiFetch<BluetoothPage<BluetoothAnchor>>(
        `/api/v2/bluetooth/anchors${query({
          scene_id: filters.sceneId,
          state: filters.state,
          serial: filters.serial,
          provider_id: filters.providerId,
          offset: filters.offset ?? 0,
          limit: filters.limit ?? 100,
        })}`,
      );
    },
    create(payload: AnchorPayload) {
      return apiFetch<BluetoothAnchor>("/api/v2/bluetooth/anchors", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    update(uid: string, revision: number, payload: Partial<AnchorPayload>) {
      return apiFetch<BluetoothAnchor>(
        `/api/v2/bluetooth/anchors/${encodeURIComponent(uid)}?revision=${revision}`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
    },
    lifecycle(
      uid: string,
      action: "activate" | "deactivate" | "maintenance" | "retire",
      revision: number,
    ) {
      return apiFetch<BluetoothAnchor>(
        `/api/v2/bluetooth/anchors/${encodeURIComponent(uid)}/${action}?revision=${revision}`,
        { method: "POST" },
      );
    },
    remove(uid: string, revision: number) {
      return apiFetch(
        `/api/v2/bluetooth/anchors/${encodeURIComponent(uid)}?revision=${revision}`,
        { method: "DELETE" },
      );
    },
  },
  tags: {
    list(
      filters: {
        state?: string;
        serial?: string;
        providerId?: string;
        offset?: number;
        limit?: number;
      } = {},
    ) {
      return apiFetch<BluetoothPage<BluetoothTag>>(
        `/api/v2/bluetooth/tags${query({
          state: filters.state,
          serial: filters.serial,
          provider_id: filters.providerId,
          offset: filters.offset ?? 0,
          limit: filters.limit ?? 100,
        })}`,
      );
    },
    create(payload: TagPayload) {
      return apiFetch<BluetoothTag>("/api/v2/bluetooth/tags", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    update(uid: string, revision: number, payload: Partial<TagPayload>) {
      return apiFetch<BluetoothTag>(
        `/api/v2/bluetooth/tags/${encodeURIComponent(uid)}?revision=${revision}`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
    },
    lifecycle(
      uid: string,
      action: "activate" | "deactivate" | "maintenance" | "retire",
      revision: number,
    ) {
      return apiFetch<BluetoothTag>(
        `/api/v2/bluetooth/tags/${encodeURIComponent(uid)}/${action}?revision=${revision}`,
        { method: "POST" },
      );
    },
    remove(uid: string, revision: number) {
      return apiFetch(
        `/api/v2/bluetooth/tags/${encodeURIComponent(uid)}?revision=${revision}`,
        { method: "DELETE" },
      );
    },
  },
  assignments: {
    list(
      filters: {
        tagId?: string;
        entityType?: string;
        entityId?: string;
        active?: boolean;
        offset?: number;
        limit?: number;
      } = {},
    ) {
      return apiFetch<BluetoothPage<BluetoothAssignment>>(
        `/api/v2/bluetooth/assignments${query({
          tag_id: filters.tagId,
          entity_type: filters.entityType,
          entity_id: filters.entityId,
          active:
            filters.active === undefined ? undefined : String(filters.active),
          offset: filters.offset ?? 0,
          limit: filters.limit ?? 200,
        })}`,
      );
    },
    create(payload: AssignmentPayload) {
      return apiFetch<BluetoothAssignment>("/api/v2/bluetooth/assignments", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    close(uid: string, revision: number) {
      return apiFetch<BluetoothAssignment>(
        `/api/v2/bluetooth/assignments/${encodeURIComponent(uid)}/close?revision=${revision}`,
        { method: "POST", body: JSON.stringify({}) },
      );
    },
  },
  calibrations: {
    list(
      filters: {
        sceneId?: string;
        anchorId?: string;
        state?: string;
        offset?: number;
        limit?: number;
      } = {},
    ) {
      return apiFetch<BluetoothPage<BluetoothCalibration>>(
        `/api/v2/bluetooth/calibrations${query({
          scene_id: filters.sceneId,
          anchor_id: filters.anchorId,
          state: filters.state,
          offset: filters.offset ?? 0,
          limit: filters.limit ?? 500,
        })}`,
      );
    },
    history(anchorId: string) {
      return apiFetch<{ items: BluetoothCalibration[]; total: number }>(
        `/api/v2/bluetooth/anchors/${encodeURIComponent(anchorId)}/calibrations`,
      );
    },
    geometry(sceneId: string) {
      return apiFetch<BluetoothGeometry>(
        `/api/v2/bluetooth/calibrations/geometry?scene_id=${encodeURIComponent(sceneId)}`,
      );
    },
    create(payload: CalibrationPayload) {
      return apiFetch<BluetoothCalibration>("/api/v2/bluetooth/calibrations", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    publish(uid: string, revision: number) {
      return apiFetch<BluetoothCalibration>(
        `/api/v2/bluetooth/calibrations/${encodeURIComponent(uid)}/publish?revision=${revision}`,
        { method: "POST" },
      );
    },
    restore(uid: string, revision: number) {
      return apiFetch<BluetoothCalibration>(
        `/api/v2/bluetooth/calibrations/${encodeURIComponent(uid)}/restore?revision=${revision}`,
        { method: "POST" },
      );
    },
  },
  surveys: {
    bias(sceneId: string) {
      return apiFetch<{
        scene_id: string;
        anchors: Record<string, BluetoothSurveyBias>;
      }>(
        `/api/v2/bluetooth/surveys/bias?scene_id=${encodeURIComponent(sceneId)}`,
      );
    },
    createBiasRevisions(sceneId: string, minimumSamples = 3) {
      return apiFetch<{
        scene_id: string;
        created: BluetoothCalibration[];
      }>(
        `/api/v2/bluetooth/surveys/bias/revisions${query({
          scene_id: sceneId,
          minimum_samples: minimumSamples,
        })}`,
        { method: "POST" },
      );
    },
    coverage(
      sceneId: string,
      bounds: {
        minX: number;
        maxX: number;
        minY: number;
        maxY: number;
        step: number;
        fixedZ?: number;
      },
    ) {
      return apiFetch<BluetoothCoverage>(
        `/api/v2/bluetooth/surveys/coverage${query({
          scene_id: sceneId,
          min_x_m: bounds.minX,
          max_x_m: bounds.maxX,
          min_y_m: bounds.minY,
          max_y_m: bounds.maxY,
          step_m: bounds.step,
          fixed_z_m: bounds.fixedZ ?? 1,
        })}`,
      );
    },
    createPoint(payload: {
      scene_id: string;
      name: string;
      x_m: number;
      y_m: number;
      z_m: number;
    }) {
      return apiFetch<BluetoothSurveyPoint>(
        "/api/v2/bluetooth/surveys/points",
        { method: "POST", body: JSON.stringify(payload) },
      );
    },
    addSample(
      pointId: string,
      payload: {
        anchor_uid: string;
        distance_m: number;
        distance_stddev_m?: number;
        quality?: number;
      },
    ) {
      return apiFetch(
        `/api/v2/bluetooth/surveys/points/${encodeURIComponent(pointId)}/samples`,
        { method: "POST", body: JSON.stringify(payload) },
      );
    },
    closePoint(pointId: string) {
      return apiFetch(
        `/api/v2/bluetooth/surveys/points/${encodeURIComponent(pointId)}/close`,
        { method: "POST" },
      );
    },
  },
  diagnostics() {
    return apiFetch<BluetoothDiagnostics>("/api/v2/bluetooth/diagnostics");
  },
};
