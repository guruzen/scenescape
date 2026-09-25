// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState } from "react";
import BluetoothCalibration from "./BluetoothCalibration";
import {
  bluetoothApi,
  type AnchorPayload,
  type AssignmentPayload,
  type BluetoothAnchor,
  type BluetoothAssignment,
  type BluetoothDiagnostics,
  type BluetoothTag,
  type TagPayload,
} from "./bluetoothApi";

type Row = Record<string, any>;
type Tab = "anchors" | "tags" | "diagnostics" | "calibration";

const deviceStates = [
  "",
  "discovered",
  "commissioned",
  "active",
  "maintenance",
  "disabled",
  "offline",
  "retired",
];

const emptyAnchor = (): AnchorPayload => ({
  serial_number: "",
  scene_id: "",
  provider_id: "",
  provider_device_id: "",
  bluetooth_address: "",
  manufacturer: "",
  model: "",
  hardware_revision: "",
  firmware_revision: "",
  capabilities: ["channel_sounding"],
});

const emptyTag = (): TagPayload => ({
  serial_number: "",
  provider_id: "",
  provider_device_id: "",
  bluetooth_address: "",
  manufacturer: "",
  model: "",
  hardware_revision: "",
  firmware_revision: "",
  capabilities: ["channel_sounding"],
});

const emptyAssignment = (tagUid = ""): AssignmentPayload => ({
  tag_uid: tagUid,
  entity_type: "asset",
  entity_id: "",
  display_name: "",
  reason: "",
});

const cleanOptional = (value: unknown) => {
  const text = String(value ?? "").trim();
  return text || undefined;
};

const parseCapabilities = (value: string) =>
  Array.from(
    new Set(
      value
        .split(",")
        .map((item) => item.trim().toLowerCase().replace(/[ -]+/g, "_"))
        .filter(Boolean),
    ),
  );

const capabilityText = (values: string[] | undefined) =>
  Array.isArray(values) ? values.join(", ") : "";

const displayTime = (value: unknown) => {
  if (!value) return "Unknown";
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.getTime())
    ? String(value)
    : parsed.toLocaleString();
};

const batteryText = (tag: BluetoothTag) =>
  tag.battery?.percent === null || tag.battery?.percent === undefined
    ? "Unknown"
    : `${Math.round(Number(tag.battery.percent))}%`;

const stateLabel = (value: string) =>
  value ? value.replaceAll("_", " ") : "unknown";

function StatusBadge({ state }: { state: string }) {
  return (
    <span className={`bt-status bt-status-${state || "unknown"}`}>
      <span aria-hidden="true" className="bt-status-dot" />
      {stateLabel(state)}
    </span>
  );
}

export default function BluetoothPositioning({
  scenes,
  isAdmin,
}: {
  scenes: Row[];
  isAdmin: boolean;
}) {
  const [tab, setTab] = useState<Tab>("anchors");
  const [anchors, setAnchors] = useState<BluetoothAnchor[]>([]);
  const [tags, setTags] = useState<BluetoothTag[]>([]);
  const [assignments, setAssignments] = useState<BluetoothAssignment[]>([]);
  const [diagnostics, setDiagnostics] = useState<BluetoothDiagnostics | null>(
    null,
  );
  const [selectedAnchor, setSelectedAnchor] = useState<BluetoothAnchor | null>(
    null,
  );
  const [selectedTag, setSelectedTag] = useState<BluetoothTag | null>(null);
  const [anchorDraft, setAnchorDraft] = useState<AnchorPayload>(emptyAnchor);
  const [tagDraft, setTagDraft] = useState<TagPayload>(emptyTag);
  const [assignmentDraft, setAssignmentDraft] =
    useState<AssignmentPayload>(emptyAssignment());
  const [anchorCapabilities, setAnchorCapabilities] =
    useState("channel_sounding");
  const [tagCapabilities, setTagCapabilities] = useState("channel_sounding");
  const [anchorSearch, setAnchorSearch] = useState("");
  const [anchorScene, setAnchorScene] = useState("");
  const [anchorState, setAnchorState] = useState("");
  const [tagSearch, setTagSearch] = useState("");
  const [tagState, setTagState] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const sceneName = (uid?: string | null) =>
    scenes.find((scene) => String(scene.uid ?? scene.id ?? "") === String(uid))
      ?.name ||
    uid ||
    "Unassigned";

  const loadAnchors = async () => {
    const result = await bluetoothApi.anchors.list({
      sceneId: anchorScene || undefined,
      state: anchorState || undefined,
      serial: anchorSearch || undefined,
    });
    setAnchors(result.items);
    setSelectedAnchor((current) => {
      if (!current) return current;
      return result.items.find((item) => item.uid === current.uid) ?? current;
    });
  };

  const loadAdminData = async () => {
    if (!isAdmin) {
      setTags([]);
      setAssignments([]);
      return;
    }
    const [tagPage, assignmentPage] = await Promise.all([
      bluetoothApi.tags.list({
        state: tagState || undefined,
        serial: tagSearch || undefined,
      }),
      bluetoothApi.assignments.list(),
    ]);
    setTags(tagPage.items);
    setAssignments(assignmentPage.items);
    setSelectedTag((current) => {
      if (!current) return current;
      return tagPage.items.find((item) => item.uid === current.uid) ?? current;
    });
  };

  const loadDiagnostics = async () => {
    setDiagnostics(await bluetoothApi.diagnostics());
  };

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      await Promise.all([loadAnchors(), loadAdminData(), loadDiagnostics()]);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // Initial load is intentionally independent of editor state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  useEffect(() => {
    const id = window.setTimeout(() => {
      void loadAnchors().catch((reason) => setError(String(reason)));
    }, 180);
    return () => window.clearTimeout(id);
  }, [anchorSearch, anchorScene, anchorState]);

  useEffect(() => {
    if (!isAdmin) return;
    const id = window.setTimeout(() => {
      void loadAdminData().catch((reason) => setError(String(reason)));
    }, 180);
    return () => window.clearTimeout(id);
  }, [tagSearch, tagState, isAdmin]);

  const openAnchor = (row: BluetoothAnchor | null) => {
    setSelectedAnchor(row);
    const next = row
      ? {
          serial_number: row.serial_number,
          scene_id: row.scene_id || "",
          provider_id: row.provider_id || "",
          provider_device_id: row.provider_device_id || "",
          bluetooth_address: row.bluetooth_address || "",
          manufacturer: row.manufacturer || "",
          model: row.model || "",
          hardware_revision: row.hardware_revision || "",
          firmware_revision: row.firmware_revision || "",
          capabilities: [...(row.capabilities || [])],
        }
      : emptyAnchor();
    setAnchorDraft(next);
    setAnchorCapabilities(capabilityText(next.capabilities));
    setMessage("");
    setError("");
  };

  const openTag = (row: BluetoothTag | null) => {
    setSelectedTag(row);
    const next = row
      ? {
          serial_number: row.serial_number,
          provider_id: row.provider_id || "",
          provider_device_id: row.provider_device_id || "",
          bluetooth_address: row.bluetooth_address || "",
          manufacturer: row.manufacturer || "",
          model: row.model || "",
          hardware_revision: row.hardware_revision || "",
          firmware_revision: row.firmware_revision || "",
          capabilities: [...(row.capabilities || [])],
        }
      : emptyTag();
    setTagDraft(next);
    setTagCapabilities(capabilityText(next.capabilities));
    setAssignmentDraft(emptyAssignment(row?.uid || ""));
    setMessage("");
    setError("");
  };

  const anchorField = (key: keyof AnchorPayload, value: unknown) =>
    setAnchorDraft((current) => ({ ...current, [key]: value }));
  const tagField = (key: keyof TagPayload, value: unknown) =>
    setTagDraft((current) => ({ ...current, [key]: value }));

  const saveAnchor = async () => {
    if (!isAdmin) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const serial = String(anchorDraft.serial_number || "").trim();
      if (!serial) throw new Error("Serial number is required.");
      const payload: AnchorPayload = {
        serial_number: serial,
        scene_id: cleanOptional(anchorDraft.scene_id),
        provider_id: cleanOptional(anchorDraft.provider_id),
        provider_device_id: cleanOptional(anchorDraft.provider_device_id),
        bluetooth_address: cleanOptional(anchorDraft.bluetooth_address),
        manufacturer: cleanOptional(anchorDraft.manufacturer),
        model: cleanOptional(anchorDraft.model),
        hardware_revision: cleanOptional(anchorDraft.hardware_revision),
        firmware_revision: cleanOptional(anchorDraft.firmware_revision),
        capabilities: parseCapabilities(anchorCapabilities),
      };
      const saved = selectedAnchor
        ? await bluetoothApi.anchors.update(
            selectedAnchor.uid,
            selectedAnchor.revision,
            payload,
          )
        : await bluetoothApi.anchors.create(payload);
      openAnchor(saved);
      setMessage(selectedAnchor ? "Anchor updated." : "Anchor commissioned.");
      await Promise.all([loadAnchors(), loadDiagnostics()]);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const anchorLifecycle = async (
    action: "activate" | "deactivate" | "maintenance" | "retire",
  ) => {
    if (!selectedAnchor || !isAdmin) return;
    if (
      action === "retire" &&
      !window.confirm(
        `Retire Bluetooth anchor ${selectedAnchor.serial_number}? This preserves its history.`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      const saved = await bluetoothApi.anchors.lifecycle(
        selectedAnchor.uid,
        action,
        selectedAnchor.revision,
      );
      openAnchor(saved);
      setMessage(`Anchor state changed to ${stateLabel(saved.state)}.`);
      await Promise.all([loadAnchors(), loadDiagnostics()]);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const removeAnchor = async () => {
    if (!selectedAnchor || !isAdmin) return;
    if (
      !window.confirm(
        `Delete Bluetooth anchor ${selectedAnchor.serial_number}? Anchors with calibration history cannot be deleted.`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await bluetoothApi.anchors.remove(
        selectedAnchor.uid,
        selectedAnchor.revision,
      );
      openAnchor(null);
      setMessage("Anchor deleted.");
      await Promise.all([loadAnchors(), loadDiagnostics()]);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const saveTag = async () => {
    if (!isAdmin) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const serial = String(tagDraft.serial_number || "").trim();
      if (!serial) throw new Error("Serial number is required.");
      const payload: TagPayload = {
        serial_number: serial,
        provider_id: cleanOptional(tagDraft.provider_id),
        provider_device_id: cleanOptional(tagDraft.provider_device_id),
        bluetooth_address: cleanOptional(tagDraft.bluetooth_address),
        manufacturer: cleanOptional(tagDraft.manufacturer),
        model: cleanOptional(tagDraft.model),
        hardware_revision: cleanOptional(tagDraft.hardware_revision),
        firmware_revision: cleanOptional(tagDraft.firmware_revision),
        capabilities: parseCapabilities(tagCapabilities),
      };
      const saved = selectedTag
        ? await bluetoothApi.tags.update(
            selectedTag.uid,
            selectedTag.revision,
            payload,
          )
        : await bluetoothApi.tags.create(payload);
      openTag(saved);
      setMessage(selectedTag ? "Tag updated." : "Tag commissioned.");
      await Promise.all([loadAdminData(), loadDiagnostics()]);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const tagLifecycle = async (
    action: "activate" | "deactivate" | "maintenance" | "retire",
  ) => {
    if (!selectedTag || !isAdmin) return;
    if (
      action === "retire" &&
      !window.confirm(
        `Retire Bluetooth tag ${selectedTag.serial_number}? Assignment history will be preserved.`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      const saved = await bluetoothApi.tags.lifecycle(
        selectedTag.uid,
        action,
        selectedTag.revision,
      );
      openTag(saved);
      setMessage(`Tag state changed to ${stateLabel(saved.state)}.`);
      await Promise.all([loadAdminData(), loadDiagnostics()]);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const removeTag = async () => {
    if (!selectedTag || !isAdmin) return;
    if (
      !window.confirm(
        `Delete Bluetooth tag ${selectedTag.serial_number}? Tags with assignment history cannot be deleted.`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await bluetoothApi.tags.remove(selectedTag.uid, selectedTag.revision);
      openTag(null);
      setMessage("Tag deleted.");
      await Promise.all([loadAdminData(), loadDiagnostics()]);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const selectedAssignments = useMemo(
    () =>
      assignments
        .filter((item) => item.tag_uid === selectedTag?.uid)
        .sort((a, b) =>
          String(b.valid_from).localeCompare(String(a.valid_from)),
        ),
    [assignments, selectedTag?.uid],
  );

  const createAssignment = async () => {
    if (!selectedTag || !isAdmin) return;
    const entityId = String(assignmentDraft.entity_id || "").trim();
    if (!entityId) {
      setError("Entity ID is required.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await bluetoothApi.assignments.create({
        tag_uid: selectedTag.uid,
        entity_type: assignmentDraft.entity_type,
        entity_id: entityId,
        display_name: cleanOptional(assignmentDraft.display_name),
        reason: cleanOptional(assignmentDraft.reason),
      });
      setAssignmentDraft(emptyAssignment(selectedTag.uid));
      setMessage("Tag assignment created.");
      await loadAdminData();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const closeAssignment = async (assignment: BluetoothAssignment) => {
    if (!isAdmin) return;
    if (
      !window.confirm(
        `Close assignment to ${assignment.display_name || assignment.entity_id}?`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      await bluetoothApi.assignments.close(assignment.uid, assignment.revision);
      setMessage("Assignment closed; history retained.");
      await loadAdminData();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const tabs: Array<{ key: Tab; label: string; disabled?: boolean }> = [
    { key: "anchors", label: "Anchors" },
    { key: "tags", label: "Tags", disabled: !isAdmin },
    { key: "diagnostics", label: "Diagnostics" },
    { key: "calibration", label: "Calibration" },
  ];

  return (
    <>
      <div className="page-header">
        <div>
          <div className="kicker">Configuration · positioning</div>
          <h1>Bluetooth positioning</h1>
          <p className="page-subtitle">
            Commission fixed anchors and mobile tags without coupling SceneScape
            to a specific Bluetooth hardware vendor.
          </p>
        </div>
        <div className="header-actions">
          <button
            className="btn"
            onClick={() => void refresh()}
            disabled={loading}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
          {isAdmin && tab === "anchors" && (
            <button
              className="btn btn-primary"
              onClick={() => openAnchor(null)}
            >
              New anchor
            </button>
          )}
          {isAdmin && tab === "tags" && (
            <button className="btn btn-primary" onClick={() => openTag(null)}>
              New tag
            </button>
          )}
        </div>
      </div>

      <nav
        className="bt-tabs panel"
        role="tablist"
        aria-label="Bluetooth positioning sections"
      >
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={tab === item.key}
            className={tab === item.key ? "bt-tab active" : "bt-tab"}
            disabled={item.disabled}
            onClick={() => setTab(item.key)}
          >
            {item.label}
            {item.disabled && <span className="bt-tab-lock">Admin</span>}
          </button>
        ))}
      </nav>

      {message && (
        <div className="notice-box" role="status" aria-live="polite">
          {message}
        </div>
      )}
      {error && (
        <div className="error-box" role="alert">
          {error}
        </div>
      )}

      {tab === "anchors" && (
        <div className="bt-layout">
          <section
            className="panel bt-list-panel"
            aria-label="Bluetooth anchors"
          >
            <div className="bt-filter-grid">
              <label>
                Search serial
                <input
                  aria-label="Search Bluetooth anchors"
                  value={anchorSearch}
                  onChange={(event) => setAnchorSearch(event.target.value)}
                  placeholder="ANCHOR-..."
                />
              </label>
              <label>
                Scene
                <select
                  aria-label="Filter anchors by scene"
                  value={anchorScene}
                  onChange={(event) => setAnchorScene(event.target.value)}
                >
                  <option value="">All authorized scenes</option>
                  {scenes.map((scene) => {
                    const uid = String(scene.uid ?? scene.id ?? "");
                    return (
                      <option key={uid} value={uid}>
                        {String(scene.name || uid)}
                      </option>
                    );
                  })}
                </select>
              </label>
              <label>
                State
                <select
                  aria-label="Filter anchors by state"
                  value={anchorState}
                  onChange={(event) => setAnchorState(event.target.value)}
                >
                  {deviceStates.map((state) => (
                    <option key={state || "all"} value={state}>
                      {state ? stateLabel(state) : "All states"}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="bt-count">{anchors.length} anchor(s) shown</div>
            <div className="bt-device-list">
              {anchors.map((anchor) => (
                <button
                  type="button"
                  key={anchor.uid}
                  className={
                    selectedAnchor?.uid === anchor.uid
                      ? "bt-device-row active"
                      : "bt-device-row"
                  }
                  onClick={() => openAnchor(anchor)}
                >
                  <span>
                    <b>{anchor.serial_number}</b>
                    <small>{sceneName(anchor.scene_id)}</small>
                    <small>
                      Provider {anchor.provider_id || "Unknown"} ·{" "}
                      {capabilityText(anchor.capabilities) || "No capabilities"}
                    </small>
                  </span>
                  <span className="bt-row-meta">
                    <StatusBadge state={anchor.state} />
                    <small>{anchor.model || "Model unknown"}</small>
                    <small>Last seen Unknown</small>
                  </span>
                </button>
              ))}
              {!anchors.length && (
                <div className="table-empty">
                  No anchors match the current filters.
                </div>
              )}
            </div>
          </section>

          <section className="panel bt-editor-panel">
            <div className="panel-title">
              <div>
                <h2>
                  {selectedAnchor
                    ? selectedAnchor.serial_number
                    : isAdmin
                      ? "Commission anchor"
                      : "Anchor details"}
                </h2>
                <p>
                  {selectedAnchor
                    ? `Revision ${selectedAnchor.revision} · ${sceneName(selectedAnchor.scene_id)}`
                    : "Serial number is the human-facing hardware identity."}
                </p>
              </div>
              {selectedAnchor && <StatusBadge state={selectedAnchor.state} />}
            </div>
            {!isAdmin && !selectedAnchor ? (
              <div className="table-empty">
                Select an anchor to inspect it. Administrator role is required
                to change Bluetooth inventory.
              </div>
            ) : (
              <>
                <div className="bt-form-grid">
                  <label>
                    Serial number
                    <input
                      value={String(anchorDraft.serial_number || "")}
                      readOnly={!isAdmin}
                      onChange={(event) =>
                        anchorField("serial_number", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    Scene
                    <select
                      value={String(anchorDraft.scene_id || "")}
                      disabled={!isAdmin}
                      onChange={(event) =>
                        anchorField("scene_id", event.target.value)
                      }
                    >
                      <option value="">Unassigned</option>
                      {scenes.map((scene) => {
                        const uid = String(scene.uid ?? scene.id ?? "");
                        return (
                          <option key={uid} value={uid}>
                            {String(scene.name || uid)}
                          </option>
                        );
                      })}
                    </select>
                  </label>
                  <label>
                    Provider ID
                    <input
                      value={String(anchorDraft.provider_id || "")}
                      readOnly={!isAdmin}
                      onChange={(event) =>
                        anchorField("provider_id", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    Provider device ID
                    <input
                      value={String(anchorDraft.provider_device_id || "")}
                      readOnly={!isAdmin}
                      onChange={(event) =>
                        anchorField("provider_device_id", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    Manufacturer
                    <input
                      value={String(anchorDraft.manufacturer || "")}
                      readOnly={!isAdmin}
                      onChange={(event) =>
                        anchorField("manufacturer", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    Model
                    <input
                      value={String(anchorDraft.model || "")}
                      readOnly={!isAdmin}
                      onChange={(event) =>
                        anchorField("model", event.target.value)
                      }
                    />
                  </label>
                  <label>
                    Bluetooth address
                    <input
                      value={String(anchorDraft.bluetooth_address || "")}
                      readOnly={!isAdmin}
                      onChange={(event) =>
                        anchorField("bluetooth_address", event.target.value)
                      }
                    />
                    <small>Transport metadata; not permanent identity.</small>
                  </label>
                  <label>
                    Capabilities
                    <input
                      value={anchorCapabilities}
                      readOnly={!isAdmin}
                      onChange={(event) =>
                        setAnchorCapabilities(event.target.value)
                      }
                      placeholder="channel_sounding, aoa"
                    />
                  </label>
                </div>

                <div className="bt-readout-grid">
                  <div>
                    <span>Last seen</span>
                    <b>Unknown</b>
                    <small>Anchor telemetry arrives in BT-10.</small>
                  </div>
                  <div>
                    <span>Calibration</span>
                    <b>Not configured</b>
                    <small>Map calibration is implemented in BT-04.</small>
                  </div>
                </div>

                {isAdmin && (
                  <div className="bt-actions">
                    <button
                      className="btn btn-primary"
                      onClick={() => void saveAnchor()}
                      disabled={busy}
                    >
                      {selectedAnchor ? "Save anchor" : "Commission anchor"}
                    </button>
                    {selectedAnchor && (
                      <>
                        <button
                          className="btn"
                          onClick={() => void anchorLifecycle("activate")}
                          disabled={busy || selectedAnchor.state === "retired"}
                        >
                          Activate
                        </button>
                        <button
                          className="btn"
                          onClick={() => void anchorLifecycle("maintenance")}
                          disabled={busy || selectedAnchor.state === "retired"}
                        >
                          Maintenance
                        </button>
                        <button
                          className="btn"
                          onClick={() => void anchorLifecycle("deactivate")}
                          disabled={busy || selectedAnchor.state === "retired"}
                        >
                          Disable
                        </button>
                        <button
                          className="btn"
                          onClick={() => void anchorLifecycle("retire")}
                          disabled={busy || selectedAnchor.state === "retired"}
                        >
                          Retire
                        </button>
                        <button
                          className="btn danger"
                          onClick={() => void removeAnchor()}
                          disabled={busy}
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}

      {tab === "tags" && isAdmin && (
        <div className="bt-layout">
          <section className="panel bt-list-panel" aria-label="Bluetooth tags">
            <div className="bt-filter-grid two">
              <label>
                Search serial
                <input
                  aria-label="Search Bluetooth tags"
                  value={tagSearch}
                  onChange={(event) => setTagSearch(event.target.value)}
                  placeholder="TAG-..."
                />
              </label>
              <label>
                State
                <select
                  aria-label="Filter tags by state"
                  value={tagState}
                  onChange={(event) => setTagState(event.target.value)}
                >
                  {deviceStates.map((state) => (
                    <option key={state || "all"} value={state}>
                      {state ? stateLabel(state) : "All states"}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="bt-count">{tags.length} tag(s) shown</div>
            <div className="bt-device-list">
              {tags.map((tag) => {
                const activeAssignment = assignments.find(
                  (item) => item.tag_uid === tag.uid && !item.valid_to,
                );
                return (
                  <button
                    type="button"
                    key={tag.uid}
                    className={
                      selectedTag?.uid === tag.uid
                        ? "bt-device-row active"
                        : "bt-device-row"
                    }
                    onClick={() => openTag(tag)}
                  >
                    <span>
                      <b>{tag.serial_number}</b>
                      <small>
                        {activeAssignment?.display_name ||
                          activeAssignment?.entity_id ||
                          "Unassigned"}
                      </small>
                      <small>
                        Provider {tag.provider_id || "Unknown"} ·{" "}
                        {capabilityText(tag.capabilities) || "No capabilities"}
                      </small>
                    </span>
                    <span className="bt-row-meta">
                      <StatusBadge state={tag.state} />
                      <small>Battery {batteryText(tag)}</small>
                      <small>Last seen {displayTime(tag.last_seen_at)}</small>
                    </span>
                  </button>
                );
              })}
              {!tags.length && (
                <div className="table-empty">
                  No tags match the current filters.
                </div>
              )}
            </div>
          </section>

          <section className="panel bt-editor-panel">
            <div className="panel-title">
              <div>
                <h2>
                  {selectedTag ? selectedTag.serial_number : "Commission tag"}
                </h2>
                <p>
                  {selectedTag
                    ? `Revision ${selectedTag.revision} · mobile positioning identity`
                    : "Create a stable SceneScape tag identity before assignment."}
                </p>
              </div>
              {selectedTag && <StatusBadge state={selectedTag.state} />}
            </div>

            <div className="bt-form-grid">
              <label>
                Serial number
                <input
                  value={String(tagDraft.serial_number || "")}
                  onChange={(event) =>
                    tagField("serial_number", event.target.value)
                  }
                />
              </label>
              <label>
                Provider ID
                <input
                  value={String(tagDraft.provider_id || "")}
                  onChange={(event) =>
                    tagField("provider_id", event.target.value)
                  }
                />
              </label>
              <label>
                Provider device ID
                <input
                  value={String(tagDraft.provider_device_id || "")}
                  onChange={(event) =>
                    tagField("provider_device_id", event.target.value)
                  }
                />
              </label>
              <label>
                Bluetooth address
                <input
                  value={String(tagDraft.bluetooth_address || "")}
                  onChange={(event) =>
                    tagField("bluetooth_address", event.target.value)
                  }
                />
              </label>
              <label>
                Manufacturer
                <input
                  value={String(tagDraft.manufacturer || "")}
                  onChange={(event) =>
                    tagField("manufacturer", event.target.value)
                  }
                />
              </label>
              <label>
                Model
                <input
                  value={String(tagDraft.model || "")}
                  onChange={(event) => tagField("model", event.target.value)}
                />
              </label>
              <label className="wide">
                Capabilities
                <input
                  value={tagCapabilities}
                  onChange={(event) => setTagCapabilities(event.target.value)}
                  placeholder="channel_sounding, battery_service"
                />
              </label>
            </div>

            <div className="bt-readout-grid">
              <div>
                <span>Battery</span>
                <b>{selectedTag ? batteryText(selectedTag) : "Unknown"}</b>
                <small>
                  {selectedTag?.battery?.observed_at
                    ? `Observed ${displayTime(selectedTag.battery.observed_at)}`
                    : "No battery telemetry received."}
                </small>
              </div>
              <div>
                <span>Last seen</span>
                <b>
                  {selectedTag
                    ? displayTime(selectedTag.last_seen_at)
                    : "Unknown"}
                </b>
                <small>Telemetry is read-only in this management UI.</small>
              </div>
            </div>

            <div className="bt-actions">
              <button
                className="btn btn-primary"
                onClick={() => void saveTag()}
                disabled={busy}
              >
                {selectedTag ? "Save tag" : "Commission tag"}
              </button>
              {selectedTag && (
                <>
                  <button
                    className="btn"
                    onClick={() => void tagLifecycle("activate")}
                    disabled={busy || selectedTag.state === "retired"}
                  >
                    Activate
                  </button>
                  <button
                    className="btn"
                    onClick={() => void tagLifecycle("maintenance")}
                    disabled={busy || selectedTag.state === "retired"}
                  >
                    Maintenance
                  </button>
                  <button
                    className="btn"
                    onClick={() => void tagLifecycle("deactivate")}
                    disabled={busy || selectedTag.state === "retired"}
                  >
                    Disable
                  </button>
                  <button
                    className="btn"
                    onClick={() => void tagLifecycle("retire")}
                    disabled={busy || selectedTag.state === "retired"}
                  >
                    Retire
                  </button>
                  <button
                    className="btn danger"
                    onClick={() => void removeTag()}
                    disabled={busy}
                  >
                    Delete
                  </button>
                </>
              )}
            </div>

            {selectedTag && (
              <section className="bt-assignments">
                <div className="bt-section-title">
                  <div>
                    <h3>Assignment history</h3>
                    <p>
                      Business identity is separate from Bluetooth transport
                      identity and is retained as an audit history.
                    </p>
                  </div>
                </div>
                <div className="bt-assignment-list">
                  {selectedAssignments.map((assignment) => (
                    <div key={assignment.uid} className="bt-assignment-row">
                      <div>
                        <b>{assignment.display_name || assignment.entity_id}</b>
                        <span>
                          {assignment.entity_type} · {assignment.entity_id}
                        </span>
                        <small>
                          {displayTime(assignment.valid_from)}
                          {assignment.valid_to
                            ? ` → ${displayTime(assignment.valid_to)}`
                            : " → active"}
                        </small>
                      </div>
                      {!assignment.valid_to && (
                        <button
                          className="btn"
                          onClick={() => void closeAssignment(assignment)}
                          disabled={busy}
                        >
                          Close assignment
                        </button>
                      )}
                    </div>
                  ))}
                  {!selectedAssignments.length && (
                    <div className="table-empty">
                      No assignment history for this tag.
                    </div>
                  )}
                </div>
                <div className="bt-assignment-form">
                  <label>
                    Type
                    <select
                      aria-label="Assignment entity type"
                      value={assignmentDraft.entity_type}
                      onChange={(event) =>
                        setAssignmentDraft((current) => ({
                          ...current,
                          entity_type: event.target.value,
                        }))
                      }
                    >
                      <option value="asset">Asset</option>
                      <option value="person">Person</option>
                      <option value="vehicle">Vehicle</option>
                      <option value="tool">Tool</option>
                      <option value="other">Other</option>
                    </select>
                  </label>
                  <label>
                    Entity ID
                    <input
                      aria-label="Assignment entity ID"
                      value={assignmentDraft.entity_id}
                      onChange={(event) =>
                        setAssignmentDraft((current) => ({
                          ...current,
                          entity_id: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label>
                    Display name
                    <input
                      value={assignmentDraft.display_name || ""}
                      onChange={(event) =>
                        setAssignmentDraft((current) => ({
                          ...current,
                          display_name: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <label>
                    Reason
                    <input
                      value={assignmentDraft.reason || ""}
                      onChange={(event) =>
                        setAssignmentDraft((current) => ({
                          ...current,
                          reason: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <button
                    className="btn btn-primary"
                    onClick={() => void createAssignment()}
                    disabled={busy}
                  >
                    Assign tag
                  </button>
                </div>
              </section>
            )}
          </section>
        </div>
      )}

      {tab === "diagnostics" && (
        <>
          <div className="bt-health-grid">
            <section className="panel bt-health-card">
              <span>Anchors visible</span>
              <strong>{diagnostics?.anchors.total ?? "—"}</strong>
              <small>
                Active {diagnostics?.anchors.by_state?.active ?? 0} · Offline{" "}
                {diagnostics?.anchors.by_state?.offline ?? 0}
              </small>
            </section>
            <section className="panel bt-health-card">
              <span>Unassigned anchors</span>
              <strong>{diagnostics?.anchors.unassigned_scene ?? "—"}</strong>
              <small>Need scene placement before positioning.</small>
            </section>
            <section className="panel bt-health-card">
              <span>Tags visible</span>
              <strong>
                {diagnostics?.tags.visible
                  ? (diagnostics.tags.total ?? 0)
                  : "Restricted"}
              </strong>
              <small>
                {diagnostics?.tags.visible
                  ? `Low battery ${diagnostics.tags.battery?.low ?? 0} · Critical ${diagnostics.tags.battery?.critical ?? 0}`
                  : "Tag identity and assignment require administrator access."}
              </small>
            </section>
            <section className="panel bt-health-card">
              <span>Scope</span>
              <strong>
                {diagnostics?.scope.all_scenes
                  ? "All scenes"
                  : diagnostics?.scope.scenes.length || 0}
              </strong>
              <small>
                {diagnostics?.scope.all_scenes
                  ? "Administrator/global scope"
                  : "Scene-scoped operator view"}
              </small>
            </section>
          </div>
          <section className="panel bt-diagnostics-detail">
            <div className="panel-title">
              <div>
                <h2>Control-plane health</h2>
                <p>
                  These values describe commissioned inventory. RF ranging and
                  solver quality are introduced by later BT iterations.
                </p>
              </div>
            </div>
            <dl>
              <div>
                <dt>Commissioned anchors</dt>
                <dd>{diagnostics?.anchors.by_state?.commissioned ?? 0}</dd>
              </div>
              <div>
                <dt>Maintenance anchors</dt>
                <dd>{diagnostics?.anchors.by_state?.maintenance ?? 0}</dd>
              </div>
              <div>
                <dt>Disabled anchors</dt>
                <dd>{diagnostics?.anchors.by_state?.disabled ?? 0}</dd>
              </div>
              <div>
                <dt>Retired anchors</dt>
                <dd>{diagnostics?.anchors.by_state?.retired ?? 0}</dd>
              </div>
            </dl>
          </section>
        </>
      )}

      {tab === "calibration" && (
        <BluetoothCalibration scenes={scenes} isAdmin={isAdmin} />
      )}
    </>
  );
}
