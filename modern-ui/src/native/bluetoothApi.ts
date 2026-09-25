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
  diagnostics() {
    return apiFetch<BluetoothDiagnostics>("/api/v2/bluetooth/diagnostics");
  },
};
