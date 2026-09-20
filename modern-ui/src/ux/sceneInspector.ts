export type SceneSelectionKind =
  "object" | "camera" | "sensor" | "region" | "tripwire";

export type SceneSelection = {
  kind: SceneSelectionKind;
  id: string;
  value: Record<string, any>;
} | null;

export type InspectorRuntime = {
  cameraTelemetry?: Record<string, any> | null;
  sensorTelemetry?: Array<Record<string, any>> | null;
};

export type InspectorField = { label: string; value: string };
export type InspectorModel = {
  title: string;
  kind: string;
  fields: InspectorField[];
  persistentData?: string;
};

const unknown = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "Unknown";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
};
const vector = (value: unknown): string =>
  Array.isArray(value) && value.length
    ? value.map((item) => Number(item).toFixed(2)).join(", ")
    : "Unknown";

export function refreshObjectSelection(
  selection: SceneSelection,
  liveObjects: Array<Record<string, any>>,
): SceneSelection {
  if (!selection || selection.kind !== "object") return selection;
  const current = liveObjects.find(
    (row, index) => String(row.id ?? index) === selection.id,
  );
  return current ? { ...selection, value: current } : selection;
}

export function buildInspectorModel(
  selection: SceneSelection,
  runtime: InspectorRuntime = {},
): InspectorModel | null {
  if (!selection) return null;
  const row = selection.value || {};
  if (selection.kind === "object") {
    const velocity =
      Array.isArray(row.velocity) && row.velocity.length >= 2
        ? row.velocity.slice(0, 3).map(Number)
        : null;
    const speed =
      velocity && velocity.slice(0, 2).every(Number.isFinite)
        ? Math.hypot(velocity[0], velocity[1]).toFixed(2)
        : "Unknown";
    const regions =
      row.regions && typeof row.regions === "object"
        ? Object.keys(row.regions).join(", ") || "None"
        : "Unknown";
    const dwellValues =
      row.regions && typeof row.regions === "object"
        ? Object.values(row.regions)
            .map((value: any) => Number(value?.dwell))
            .filter(Number.isFinite)
        : [];
    const dwell = dwellValues.length
      ? `${Math.max(...dwellValues).toFixed(1)} s`
      : "Unknown";
    const visibility = Array.isArray(row.visibility)
      ? row.visibility.join(", ") || "None"
      : "Unknown";
    return {
      title: `Object ${unknown(row.id ?? selection.id)}`,
      kind: "Tracked object",
      fields: [
        { label: "Category", value: unknown(row.category ?? row.type) },
        { label: "Position", value: vector(row.translation) },
        { label: "Velocity", value: vector(row.velocity) },
        { label: "Speed", value: speed === "Unknown" ? speed : `${speed} m/s` },
        { label: "Regions", value: regions },
        { label: "Dwell", value: dwell },
        { label: "Visible cameras", value: visibility },
      ],
      persistentData:
        row.persistent_data && typeof row.persistent_data === "object"
          ? JSON.stringify(row.persistent_data, null, 2)
          : undefined,
    };
  }
  if (selection.kind === "camera") {
    const telemetry = runtime.cameraTelemetry || {};
    return {
      title: unknown(row.name ?? selection.id),
      kind: "Camera",
      fields: [
        { label: "ID", value: selection.id },
        { label: "Scene", value: unknown(row.scene ?? row.scene_id) },
        {
          label: "FPS",
          value:
            telemetry.fps === null || telemetry.fps === undefined
              ? "Unknown"
              : Number(telemetry.fps).toFixed(1),
        },
        { label: "Detections", value: unknown(telemetry.detections) },
        {
          label: "Feed",
          value:
            telemetry.stale === true
              ? "Stale"
              : telemetry.stale === false
                ? "Receiving"
                : "Unknown",
        },
        {
          label: "Last observation",
          value: unknown(telemetry.last_observation),
        },
        {
          label: "Calibration",
          value: unknown(row.calibration_status ?? row.calibrated),
        },
        {
          label: "Pipeline",
          value: unknown(row.pipeline ?? row.pipeline_status),
        },
      ],
    };
  }
  if (selection.kind === "sensor") {
    const latest = runtime.sensorTelemetry?.[0] || null;
    return {
      title: unknown(row.name ?? selection.id),
      kind: "Sensor",
      fields: [
        { label: "ID", value: selection.id },
        { label: "Type", value: unknown(row.singleton_type ?? row.type) },
        { label: "Area", value: unknown(row.area) },
        {
          label: "Latest value",
          value: latest
            ? unknown(latest.payload?.value ?? latest.value ?? latest.payload)
            : "Unknown",
        },
        {
          label: "Latest observation",
          value: latest
            ? unknown(latest.timestamp ?? latest.observed_at)
            : "Unknown",
        },
      ],
    };
  }
  if (selection.kind === "region") {
    return {
      title: unknown(row.name ?? selection.id),
      kind: "Region",
      fields: [
        { label: "ID", value: selection.id },
        {
          label: "Geometry",
          value: `${Array.isArray(row.points) ? row.points.length : 0} points`,
        },
        {
          label: "Height",
          value:
            row.height === null || row.height === undefined
              ? "Unknown"
              : `${Number(row.height).toFixed(2)} m`,
        },
        { label: "Occupancy", value: unknown(row.occupancy) },
        {
          label: "Threshold",
          value: unknown(row.threshold ?? row.max_occupancy),
        },
        {
          label: "Dwell threshold",
          value: unknown(row.dwell_time ?? row.dwell_threshold),
        },
      ],
    };
  }
  return {
    title: unknown(row.name ?? selection.id),
    kind: "Tripwire",
    fields: [
      { label: "ID", value: selection.id },
      {
        label: "Geometry",
        value: `${Array.isArray(row.points) ? row.points.length : 0} points`,
      },
      { label: "Direction", value: unknown(row.direction ?? row.directional) },
      {
        label: "Height",
        value:
          row.height === null || row.height === undefined
            ? "Unknown"
            : `${Number(row.height).toFixed(2)} m`,
      },
      { label: "Recent event", value: unknown(row.recent_event) },
    ],
  };
}
