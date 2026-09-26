// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState, type MouseEvent } from "react";
import { apiObjectUrl } from "../api/client";
import {
  bluetoothApi,
  type BluetoothAnchor,
  type BluetoothCalibration,
  type BluetoothCoverage,
  type BluetoothGeometry,
  type BluetoothSurveyBias,
  type CalibrationPayload,
} from "./bluetoothApi";

type Row = Record<string, any>;

const rowId = (row: Row) => String(row.uid ?? row.id ?? "");
const rowName = (row: Row) => String(row.name ?? rowId(row));
const imagePath = (scene: Row | undefined) => {
  if (!scene) return "";
  const values = [scene.thumbnail, scene.map].map((value) =>
    String(value || ""),
  );
  return (
    values.find((value) => /^\/media\/.+\.(png|jpe?g|webp)$/i.test(value)) || ""
  );
};

const roundCoordinate = (value: number) => Math.round(value * 1000) / 1000;
const displayNumber = (value: number) =>
  Number.isFinite(value) ? value.toFixed(2) : "—";

const coverageBounds = (rows: BluetoothCalibration[]) => {
  const active = rows.filter((row) => row.state === "active");
  const values = active.length ? active : rows.filter((row) => row.state !== "retired");
  const xs = values.map((row) => Number(row.position.x_m)).filter(Number.isFinite);
  const ys = values.map((row) => Number(row.position.y_m)).filter(Number.isFinite);
  if (!xs.length || !ys.length) {
    return { minX: 0, maxX: 10, minY: 0, maxY: 10, step: 1 };
  }
  const minX = Math.min(...xs) - 1;
  const maxX = Math.max(...xs) + 1;
  const minY = Math.min(...ys) - 1;
  const maxY = Math.max(...ys) + 1;
  const span = Math.max(maxX - minX, maxY - minY, 1);
  return {
    minX,
    maxX,
    minY,
    maxY,
    step: Math.max(0.5, Math.min(2, span / 12)),
  };
};

const draftFromCalibration = (
  row: BluetoothCalibration | undefined,
): CalibrationPayload => ({
  anchor_uid: row?.anchor_uid || "",
  scene_id: row?.scene_id || "",
  x_m: Number(row?.position.x_m ?? 0),
  y_m: Number(row?.position.y_m ?? 0),
  z_m: Number(row?.position.z_m ?? 2.5),
  yaw_deg: Number(row?.orientation.yaw_deg ?? 0),
  pitch_deg: Number(row?.orientation.pitch_deg ?? 0),
  roll_deg: Number(row?.orientation.roll_deg ?? 0),
  z_source: row?.z_source || "measured",
  details: {},
});

function CalibrationMap({
  scene,
  anchors,
  calibrations,
  selectedAnchorId,
  draft,
  hasPlacement,
  editable,
  coverage,
  showGeometryCoverage,
  showObservedRf,
  showSurveyLinks,
  onPlace,
  onSelectAnchor,
}: {
  scene: Row | undefined;
  anchors: BluetoothAnchor[];
  calibrations: BluetoothCalibration[];
  selectedAnchorId: string;
  draft: CalibrationPayload;
  hasPlacement: boolean;
  editable: boolean;
  coverage: BluetoothCoverage | null;
  showGeometryCoverage: boolean;
  showObservedRf: boolean;
  showSurveyLinks: boolean;
  onPlace: (xM: number, yM: number) => void;
  onSelectAnchor: (uid: string) => void;
}) {
  const [url, setUrl] = useState("");
  const [size, setSize] = useState<[number, number]>([1000, 700]);
  const path = imagePath(scene);
  const scale = Math.max(1, Number(scene?.scale || 100));

  useEffect(() => {
    let alive = true;
    let current = "";
    setUrl("");
    if (!path) return;
    void apiObjectUrl(path)
      .then((next) => {
        if (!alive) {
          URL.revokeObjectURL(next);
          return;
        }
        const image = new Image();
        image.onload = () => {
          if (!alive) {
            URL.revokeObjectURL(next);
            return;
          }
          setSize([
            Math.max(1, image.naturalWidth),
            Math.max(1, image.naturalHeight),
          ]);
          current = next;
          setUrl(next);
        };
        image.onerror = () => URL.revokeObjectURL(next);
        image.src = next;
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (current) URL.revokeObjectURL(current);
    };
  }, [path]);

  const latest = useMemo(() => {
    const result = new Map<string, BluetoothCalibration>();
    calibrations
      .filter((row) => row.state !== "retired")
      .forEach((row) => {
        const current = result.get(row.anchor_uid);
        if (
          !current ||
          row.calibration_revision > current.calibration_revision
        ) {
          result.set(row.anchor_uid, row);
        }
      });
    return result;
  }, [calibrations]);

  const toPixel = (xM: number, yM: number) => [
    xM * scale,
    size[1] - yM * scale,
  ];

  const place = (event: MouseEvent<SVGSVGElement>) => {
    if (!editable || !selectedAnchorId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const px =
      ((event.clientX - rect.left) / Math.max(rect.width, 1)) * size[0];
    const py =
      ((event.clientY - rect.top) / Math.max(rect.height, 1)) * size[1];
    onPlace(
      roundCoordinate(px / scale),
      roundCoordinate((size[1] - py) / scale),
    );
  };

  const selectedAnchor = anchors.find((row) => row.uid === selectedAnchorId);
  const selectedMarker = hasPlacement
    ? { x_m: draft.x_m, y_m: draft.y_m }
    : undefined;

  return (
    <div className="bt-cal-map-wrap">
      <svg
        className="bt-cal-map"
        viewBox={`0 0 ${size[0]} ${size[1]}`}
        aria-label="Bluetooth anchor calibration map"
        role="img"
        onClick={place}
      >
        {url && (
          <image
            href={url}
            x="0"
            y="0"
            width={size[0]}
            height={size[1]}
            preserveAspectRatio="none"
          />
        )}
        {!url && (
          <rect width={size[0]} height={size[1]} className="bt-cal-grid-bg" />
        )}
        {showGeometryCoverage &&
          coverage?.theoretical_geometry.cells.map((cell, index) => {
            const [cx, cy] = toPixel(cell.x_m, cell.y_m);
            return (
              <circle
                key={`gdop-${index}`}
                cx={cx}
                cy={cy}
                r={Math.max(5, scale * 0.18)}
                className={`bt-cal-gdop-cell ${cell.geometry_state}`}
                aria-label={`Geometry ${cell.geometry_state}, GDOP ${cell.gdop ?? "unavailable"}`}
              />
            );
          })}
        {showSurveyLinks &&
          coverage?.observed_rf.points.flatMap((point) => {
            const [sx, sy] = toPixel(
              Number(point.position[0] || 0),
              Number(point.position[1] || 0),
            );
            return anchors.flatMap((anchor) => {
              const row = latest.get(anchor.uid);
              if (!row) return [];
              const [ax, ay] = toPixel(row.position.x_m, row.position.y_m);
              return [
                <line
                  key={`survey-link-${point.survey_point_uid}-${anchor.uid}`}
                  x1={sx}
                  y1={sy}
                  x2={ax}
                  y2={ay}
                  className="bt-cal-survey-link"
                />,
              ];
            });
          })}
        {showObservedRf &&
          coverage?.observed_rf.points.map((point) => {
            const [cx, cy] = toPixel(
              Number(point.position[0] || 0),
              Number(point.position[1] || 0),
            );
            return (
              <g
                key={point.survey_point_uid}
                className="bt-cal-survey-point"
                aria-label={`Observed RF survey ${point.name}, ${point.sample_count} samples`}
              >
                <rect x={cx - 7} y={cy - 7} width="14" height="14" rx="3" />
                <text x={cx + 11} y={cy - 9}>
                  {point.name}
                </text>
              </g>
            );
          })}
        {anchors.map((anchor) => {
          const row = latest.get(anchor.uid);
          if (!row || anchor.uid === selectedAnchorId) return null;
          const [cx, cy] = toPixel(row.position.x_m, row.position.y_m);
          return (
            <g
              key={anchor.uid}
              className="bt-cal-anchor-marker"
              role="button"
              tabIndex={0}
              aria-label={`Select anchor ${anchor.serial_number}`}
              onClick={(event) => {
                event.stopPropagation();
                onSelectAnchor(anchor.uid);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectAnchor(anchor.uid);
                }
              }}
            >
              <circle cx={cx} cy={cy} r="11" />
              <text x={cx + 15} y={cy - 12}>
                {anchor.serial_number}
              </text>
            </g>
          );
        })}
        {selectedMarker &&
          selectedAnchor &&
          (() => {
            const [cx, cy] = toPixel(selectedMarker.x_m, selectedMarker.y_m);
            return (
              <g className="bt-cal-anchor-marker selected">
                <circle cx={cx} cy={cy} r="13" />
                <text x={cx + 17} y={cy - 14}>
                  {selectedAnchor.serial_number}
                </text>
              </g>
            );
          })()}
      </svg>
      <div className="bt-cal-map-note">
        <b>{scene ? rowName(scene) : "No scene selected"}</b>
        <span>
          Scale {scale.toFixed(2)} px/m · stored as scene-local metres · Y axis
          is inverted from image pixels.
        </span>
      </div>
      {!url && (
        <div className="map-watermark">
          No renderable floor image is available. Coordinates can still be
          authored on the metre canvas.
        </div>
      )}
    </div>
  );
}

export default function BluetoothCalibration({
  scenes,
  isAdmin,
}: {
  scenes: Row[];
  isAdmin: boolean;
}) {
  const [sceneId, setSceneId] = useState(() =>
    scenes.length ? rowId(scenes[0]) : "",
  );
  const [anchors, setAnchors] = useState<BluetoothAnchor[]>([]);
  const [calibrations, setCalibrations] = useState<BluetoothCalibration[]>([]);
  const [geometry, setGeometry] = useState<BluetoothGeometry | null>(null);
  const [coverage, setCoverage] = useState<BluetoothCoverage | null>(null);
  const [bias, setBias] = useState<Record<string, BluetoothSurveyBias>>({});
  const [showGeometryCoverage, setShowGeometryCoverage] = useState(false);
  const [showObservedRf, setShowObservedRf] = useState(true);
  const [showSurveyLinks, setShowSurveyLinks] = useState(false);
  const [selectedAnchorId, setSelectedAnchorId] = useState("");
  const [draft, setDraft] = useState<CalibrationPayload>(
    draftFromCalibration(undefined),
  );
  const [hasPlacement, setHasPlacement] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const scene = scenes.find((row) => rowId(row) === sceneId);
  const selectedAnchor = anchors.find((row) => row.uid === selectedAnchorId);
  const history = useMemo(
    () =>
      calibrations
        .filter((row) => row.anchor_uid === selectedAnchorId)
        .sort((a, b) => b.calibration_revision - a.calibration_revision),
    [calibrations, selectedAnchorId],
  );
  const workingCalibration =
    history.find((row) => row.state === "draft") ||
    history.find((row) => row.state === "active") ||
    history[0];
  const active = history.find((row) => row.state === "active");
  const latestDraft = history.find((row) => row.state === "draft");

  const selectAnchor = (
    uid: string,
    rows = calibrations,
    clearFeedback = true,
  ) => {
    setSelectedAnchorId(uid);
    const ordered = rows
      .filter((item) => item.anchor_uid === uid)
      .sort((a, b) => b.calibration_revision - a.calibration_revision);
    const row =
      ordered.find((item) => item.state === "draft") ||
      ordered.find((item) => item.state === "active") ||
      ordered[0];
    setDraft({
      ...draftFromCalibration(row),
      anchor_uid: uid,
      scene_id: sceneId,
    });
    setHasPlacement(Boolean(row));
    if (clearFeedback) {
      setMessage("");
      setError("");
    }
  };

  const load = async () => {
    if (!sceneId) {
      setAnchors([]);
      setCalibrations([]);
      setGeometry(null);
      setCoverage(null);
      setBias({});
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [anchorPage, calibrationPage, geometryValue] = await Promise.all([
        bluetoothApi.anchors.list({ sceneId, limit: 200 }),
        bluetoothApi.calibrations.list({ sceneId, limit: 500 }),
        bluetoothApi.calibrations.geometry(sceneId),
      ]);
      setAnchors(anchorPage.items);
      setCalibrations(calibrationPage.items);
      setGeometry(geometryValue);
      const bounds = coverageBounds(calibrationPage.items);
      const [biasValue, coverageValue] = await Promise.all([
        bluetoothApi.surveys.bias(sceneId),
        bluetoothApi.surveys.coverage(sceneId, bounds),
      ]);
      setBias(biasValue.anchors);
      setCoverage(coverageValue);
      const nextAnchor =
        anchorPage.items.find((row) => row.uid === selectedAnchorId)?.uid ||
        anchorPage.items[0]?.uid ||
        "";
      if (nextAnchor) {
        const ordered = calibrationPage.items
          .filter((item) => item.anchor_uid === nextAnchor)
          .sort((a, b) => b.calibration_revision - a.calibration_revision);
        const row =
          ordered.find((item) => item.state === "draft") ||
          ordered.find((item) => item.state === "active") ||
          ordered[0];
        setSelectedAnchorId(nextAnchor);
        setDraft({
          ...draftFromCalibration(row),
          anchor_uid: nextAnchor,
          scene_id: sceneId,
        });
        setHasPlacement(Boolean(row));
      } else {
        setSelectedAnchorId("");
        setDraft({
          ...draftFromCalibration(undefined),
          anchor_uid: "",
          scene_id: sceneId,
        });
        setHasPlacement(false);
      }
    } catch (reason) {
      setError(String(reason));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!sceneId && scenes.length) setSceneId(rowId(scenes[0]));
  }, [sceneId, scenes]);

  useEffect(() => {
    void load();
    // Reload is intentionally keyed by selected scene only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneId]);

  const setNumber = (
    key: "x_m" | "y_m" | "z_m" | "yaw_deg" | "pitch_deg" | "roll_deg",
    raw: string,
  ) => {
    const value = Number(raw);
    if (!Number.isFinite(value)) return;
    setDraft((current) => ({ ...current, [key]: value }));
    if (key === "x_m" || key === "y_m") setHasPlacement(true);
  };

  const saveDraft = async () => {
    if (!isAdmin || !selectedAnchor || !sceneId || !hasPlacement) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const saved = await bluetoothApi.calibrations.create({
        ...draft,
        anchor_uid: selectedAnchor.uid,
        scene_id: sceneId,
        details: {
          source: "floor_map",
          map_scale_px_per_m: Number(scene?.scale || 100),
        },
      });
      setMessage(
        `Draft revision ${saved.calibration_revision} saved for ${selectedAnchor.serial_number}.`,
      );
      await load();
      selectAnchor(
        selectedAnchor.uid,
        [saved, ...calibrations.filter((row) => row.uid !== saved.uid)],
        false,
      );
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const publish = async (row: BluetoothCalibration) => {
    if (!isAdmin) return;
    if (
      !window.confirm(
        `Publish calibration revision ${row.calibration_revision} for ${selectedAnchor?.serial_number || row.anchor_uid}?`,
      )
    )
      return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const saved = await bluetoothApi.calibrations.publish(
        row.uid,
        row.revision,
      );
      setMessage(
        `Calibration revision ${saved.calibration_revision} is now active.`,
      );
      await load();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const restore = async (row: BluetoothCalibration) => {
    if (!isAdmin) return;
    if (
      !window.confirm(
        `Restore retired calibration revision ${row.calibration_revision}? The current active revision will be retired.`,
      )
    )
      return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const saved = await bluetoothApi.calibrations.restore(
        row.uid,
        row.revision,
      );
      setMessage(
        `Calibration revision ${saved.calibration_revision} restored as active.`,
      );
      await load();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  const createBiasDrafts = async () => {
    if (!isAdmin || !sceneId) return;
    if (
      !window.confirm(
        "Create draft calibration revisions with the current robust survey bias estimates? Existing active revisions remain active until explicitly published.",
      )
    )
      return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const result = await bluetoothApi.surveys.createBiasRevisions(sceneId, 3);
      setMessage(
        `${result.created.length} bias-corrected calibration draft(s) created. Review them before publishing.`,
      );
      await load();
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bt-cal-workspace">
      <section className="panel bt-cal-toolbar">
        <div>
          <div className="kicker">BT-04 · scene-local calibration</div>
          <h2>Anchor calibration</h2>
          <p>
            Place anchors in SceneScape metres, review geometry, then publish a
            reversible calibration revision.
          </p>
        </div>
        <div className="bt-cal-toolbar-fields">
          <label>
            Scene
            <select
              aria-label="Calibration scene"
              value={sceneId}
              onChange={(event) => setSceneId(event.target.value)}
            >
              {scenes.map((row) => (
                <option key={rowId(row)} value={rowId(row)}>
                  {rowName(row)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Anchor
            <select
              aria-label="Calibration anchor"
              value={selectedAnchorId}
              onChange={(event) => selectAnchor(event.target.value)}
            >
              <option value="">Select anchor</option>
              {anchors.map((row) => (
                <option key={row.uid} value={row.uid}>
                  {row.serial_number}
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn"
            disabled={loading}
            onClick={() => void load()}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </section>

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

      <div className="bt-cal-main-grid">
        <section className="panel bt-cal-map-panel">
          <div className="panel-title">
            <div>
              <h2>Floor-map placement</h2>
              <p>
                Click the map to set X/Y. Coordinates are converted through the
                scene scale before they are sent to the API.
              </p>
            </div>
            {active && (
              <span className="bt-status bt-status-active">
                <span className="bt-status-dot" aria-hidden="true" />
                active r{active.calibration_revision}
              </span>
            )}
          </div>
          <div className="bt-cal-overlay-controls" aria-label="Bluetooth calibration diagnostic overlays">
            <label>
              <input
                type="checkbox"
                checked={showGeometryCoverage}
                onChange={(event) => setShowGeometryCoverage(event.target.checked)}
              />
              Theoretical GDOP
            </label>
            <label>
              <input
                type="checkbox"
                checked={showObservedRf}
                onChange={(event) => setShowObservedRf(event.target.checked)}
              />
              Observed RF surveys
            </label>
            <label>
              <input
                type="checkbox"
                checked={showSurveyLinks}
                onChange={(event) => setShowSurveyLinks(event.target.checked)}
              />
              Survey-anchor links
            </label>
            <span>
              Geometry model: {coverage?.theoretical_geometry.model || "not loaded"} ·
              observed source: {coverage?.observed_rf.source || "not loaded"}
            </span>
          </div>
          <CalibrationMap
            scene={scene}
            anchors={anchors}
            calibrations={calibrations}
            selectedAnchorId={selectedAnchorId}
            draft={draft}
            hasPlacement={hasPlacement}
            editable={isAdmin}
            coverage={coverage}
            showGeometryCoverage={showGeometryCoverage}
            showObservedRf={showObservedRf}
            showSurveyLinks={showSurveyLinks}
            onPlace={(xM, yM) => {
              setDraft((current) => ({
                ...current,
                x_m: xM,
                y_m: yM,
                anchor_uid: selectedAnchorId,
                scene_id: sceneId,
              }));
              setHasPlacement(true);
            }}
            onSelectAnchor={(uid) => selectAnchor(uid)}
          />
        </section>

        <aside className="panel bt-cal-editor">
          <div className="panel-title">
            <div>
              <h2>{selectedAnchor?.serial_number || "Select an anchor"}</h2>
              <p>
                {workingCalibration
                  ? `Working revision ${workingCalibration.calibration_revision} · ${workingCalibration.state}`
                  : "No calibration history yet."}
              </p>
            </div>
          </div>
          <div className="bt-cal-coordinate-grid">
            <label>
              X (m)
              <input
                aria-label="Calibration X metres"
                type="number"
                step="0.001"
                value={draft.x_m}
                readOnly={!isAdmin}
                onChange={(event) => setNumber("x_m", event.target.value)}
              />
            </label>
            <label>
              Y (m)
              <input
                aria-label="Calibration Y metres"
                type="number"
                step="0.001"
                value={draft.y_m}
                readOnly={!isAdmin}
                onChange={(event) => setNumber("y_m", event.target.value)}
              />
            </label>
            <label>
              Z / mounting height (m)
              <input
                aria-label="Calibration Z metres"
                type="number"
                step="0.01"
                value={draft.z_m}
                readOnly={!isAdmin}
                onChange={(event) => setNumber("z_m", event.target.value)}
              />
            </label>
            <label>
              Z provenance
              <select
                aria-label="Calibration Z provenance"
                value={draft.z_source}
                disabled={!isAdmin}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    z_source: event.target
                      .value as CalibrationPayload["z_source"],
                  }))
                }
              >
                <option value="measured">Measured</option>
                <option value="surveyed">Surveyed</option>
                <option value="default">Default / constrained</option>
              </select>
            </label>
            <label>
              Yaw (°)
              <input
                aria-label="Calibration yaw degrees"
                type="number"
                step="1"
                value={draft.yaw_deg}
                readOnly={!isAdmin}
                onChange={(event) => setNumber("yaw_deg", event.target.value)}
              />
            </label>
            <label>
              Pitch (°)
              <input
                aria-label="Calibration pitch degrees"
                type="number"
                step="1"
                value={draft.pitch_deg}
                readOnly={!isAdmin}
                onChange={(event) => setNumber("pitch_deg", event.target.value)}
              />
            </label>
            <label>
              Roll (°)
              <input
                aria-label="Calibration roll degrees"
                type="number"
                step="1"
                value={draft.roll_deg}
                readOnly={!isAdmin}
                onChange={(event) => setNumber("roll_deg", event.target.value)}
              />
            </label>
          </div>
          <div className="bt-cal-coordinate-readout">
            <span>Solver frame</span>
            <b>
              ({displayNumber(draft.x_m)}, {displayNumber(draft.y_m)},{" "}
              {displayNumber(draft.z_m)}) m
            </b>
            <small>
              Authoritative frame:{" "}
              {workingCalibration?.coordinate_frame || "scene_local_m"}
            </small>
          </div>
          {workingCalibration?.parent_projection && (
            <div className="bt-cal-parent-projection">
              <span>
                Parent projection ·{" "}
                {workingCalibration.parent_projection.parent_scene_id}
              </span>
              <b>
                (
                {displayNumber(
                  workingCalibration.parent_projection.position.x_m,
                )}
                ,{" "}
                {displayNumber(
                  workingCalibration.parent_projection.position.y_m,
                )}
                ,{" "}
                {displayNumber(
                  workingCalibration.parent_projection.position.z_m,
                )}
                ) m
              </b>
              <small>
                Informational only; stored calibration remains scene-local.
              </small>
            </div>
          )}
          {isAdmin && (
            <div className="bt-actions">
              <button
                className="btn btn-primary"
                disabled={busy || !selectedAnchor || !hasPlacement}
                onClick={() => void saveDraft()}
              >
                Save new draft
              </button>
              {latestDraft && (
                <button
                  className="btn"
                  disabled={busy}
                  onClick={() => void publish(latestDraft)}
                >
                  Publish draft r{latestDraft.calibration_revision}
                </button>
              )}
            </div>
          )}
        </aside>
      </div>

      <div className="bt-cal-bottom-grid">
        <section className="panel bt-cal-geometry">
          <div className="panel-title">
            <div>
              <h2>Geometry quality</h2>
              <p>
                Fast pre-solver checks for insufficient, duplicate and
                near-collinear anchor layouts.
              </p>
            </div>
            <span
              className={
                geometry?.ready_for_2d
                  ? "bt-geometry-state ready"
                  : "bt-geometry-state warning"
              }
            >
              {geometry?.ready_for_2d ? "2D ready" : "Needs attention"}
            </span>
          </div>
          <div className="bt-cal-geometry-metrics">
            <div>
              <span>Anchors</span>
              <b>{geometry?.anchor_count ?? 0}</b>
            </div>
            <div>
              <span>Max span</span>
              <b>{displayNumber(geometry?.max_span_m ?? 0)} m</b>
            </div>
            <div>
              <span>Spread ratio</span>
              <b>{(geometry?.spread_ratio ?? 0).toFixed(3)}</b>
            </div>
          </div>
          <div className="bt-cal-warning-list">
            {geometry?.warnings.map((warning, index) => (
              <div
                key={`${warning.code}-${index}`}
                className={`bt-cal-warning ${warning.severity}`}
              >
                <b>{warning.code.replaceAll("_", " ")}</b>
                <span>{warning.message}</span>
              </div>
            ))}
            {geometry && !geometry.warnings.length && (
              <div className="bt-cal-good">
                No baseline geometry warnings for the current draft/active
                layout.
              </div>
            )}
          </div>
          <div className="bt-cal-survey-diagnostics">
            <div className="bt-cal-survey-heading">
              <div>
                <h3>Survey bias & coverage</h3>
                <p>
                  Observed RF bias is estimated independently from theoretical
                  geometry. Draft corrections never publish automatically.
                </p>
              </div>
              {isAdmin && (
                <button
                  className="btn"
                  disabled={busy || !Object.values(bias).some((item) => item.accepted_count >= 3)}
                  onClick={() => void createBiasDrafts()}
                >
                  Create bias-corrected drafts
                </button>
              )}
            </div>
            <div className="bt-cal-bias-list">
              {Object.values(bias)
                .sort((a, b) => a.anchor_id.localeCompare(b.anchor_id))
                .map((item) => (
                  <div key={item.anchor_id} className="bt-cal-bias-row">
                    <b>{item.anchor_id}</b>
                    <span>{item.status.replaceAll("_", " ")}</span>
                    <span>
                      Bias{" "}
                      {item.bias_m === null || item.bias_m === undefined
                        ? "—"
                        : `${Number(item.bias_m).toFixed(3)} m`}
                    </span>
                    <span>
                      σ{" "}
                      {item.stddev_m === null || item.stddev_m === undefined
                        ? "—"
                        : `${Number(item.stddev_m).toFixed(3)} m`}
                    </span>
                    <span>
                      {item.accepted_count}/{item.sample_count} accepted
                      {item.rejected_count
                        ? ` · ${item.rejected_count} rejected`
                        : ""}
                    </span>
                  </div>
                ))}
              {!Object.keys(bias).length && (
                <div className="table-empty">No survey samples are available.</div>
              )}
            </div>
            <div className="bt-cal-coverage-summary">
              <span>
                Theoretical cells{" "}
                <b>{coverage?.theoretical_geometry.cells.length ?? 0}</b>
              </span>
              <span>
                Observed survey points <b>{coverage?.observed_rf.points.length ?? 0}</b>
              </span>
            </div>
          </div>
        </section>

        <section className="panel bt-cal-history">
          <div className="panel-title">
            <div>
              <h2>Revision history</h2>
              <p>
                Publishing retires the prior active revision. Any retired
                revision can be restored explicitly.
              </p>
            </div>
          </div>
          <div className="bt-cal-history-list">
            {history.map((row) => (
              <div key={row.uid} className="bt-cal-history-row">
                <div>
                  <b>
                    r{row.calibration_revision} · {row.state}
                  </b>
                  <span>
                    ({displayNumber(row.position.x_m)},{" "}
                    {displayNumber(row.position.y_m)},{" "}
                    {displayNumber(row.position.z_m)}) m
                  </span>
                  <small>
                    {row.z_source} Z · {row.created_by}
                  </small>
                </div>
                {isAdmin && row.state === "draft" && (
                  <button
                    className="btn"
                    disabled={busy}
                    onClick={() => void publish(row)}
                  >
                    Publish
                  </button>
                )}
                {isAdmin && row.state === "retired" && (
                  <button
                    className="btn"
                    disabled={busy}
                    onClick={() => void restore(row)}
                  >
                    Restore
                  </button>
                )}
              </div>
            ))}
            {!history.length && (
              <div className="table-empty">
                Select and place an anchor to create its first calibration
                revision.
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
