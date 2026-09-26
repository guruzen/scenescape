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
    const fusion =
      row.fusion && typeof row.fusion === "object" ? row.fusion : null;
    const fusedBluetooth =
      row.source_objects?.bluetooth?.bluetooth &&
      typeof row.source_objects.bluetooth.bluetooth === "object"
        ? row.source_objects.bluetooth.bluetooth
        : null;
    const bluetooth =
      row.bluetooth && typeof row.bluetooth === "object"
        ? row.bluetooth
        : fusedBluetooth;
    const method = String(bluetooth?.method || "").toLowerCase();
    const sourceLabel = fusion
      ? "Vision + Bluetooth fusion"
      : method === "channel_sounding"
        ? "Bluetooth · Channel Sounding"
        : method === "aoa"
          ? "Bluetooth · AoA"
          : method === "rssi"
            ? "Bluetooth · RSSI"
            : bluetooth
              ? "Bluetooth"
              : unknown(row.source ?? "vision");
    const uncertainty = Number(bluetooth?.horizontal_uncertainty_m);
    const batteryPercent = Number(bluetooth?.battery?.percent);
    const batteryStatus = String(bluetooth?.battery?.status || "unknown");
    const anchorIds = Array.isArray(bluetooth?.anchor_ids)
      ? bluetooth.anchor_ids.map(String).filter(Boolean)
      : [];
    const fusionConfidence = Number(fusion?.confidence);
    const fusionFields: InspectorField[] = fusion
      ? [
          { label: "Source", value: sourceLabel },
          {
            label: "Fusion confidence",
            value: Number.isFinite(fusionConfidence)
              ? `${Math.round(fusionConfidence * 100)}%`
              : "Unknown",
          },
          {
            label: "Vision source",
            value: unknown(fusion?.source_ids?.vision ?? fusion?.vision_object_id),
          },
          {
            label: "Bluetooth source",
            value: unknown(
              fusion?.source_ids?.bluetooth ??
                (fusion?.bluetooth_tag_id
                  ? `bt:${fusion.bluetooth_tag_id}`
                  : undefined),
            ),
          },
          { label: "Identity source", value: unknown(fusion?.identity_source) },
        ]
      : [];
    const bluetoothFields: InspectorField[] = bluetooth
      ? [
          ...(!fusion ? [{ label: "Source", value: sourceLabel }] : []),
          { label: "Position state", value: unknown(bluetooth.state) },
          {
            label: "Horizontal uncertainty",
            value: Number.isFinite(uncertainty)
              ? `${uncertainty.toFixed(2)} m`
              : "Unknown",
          },
          {
            label: "Anchors used",
            value: anchorIds.length
              ? `${unknown(bluetooth.anchors_used)} · ${anchorIds.join(", ")}`
              : unknown(bluetooth.anchors_used),
          },
          {
            label: "Freshness",
            value: bluetooth.predicted
              ? `Predicted · last measured ${unknown(bluetooth.last_measured_at)}`
              : `Measured · ${unknown(bluetooth.last_measured_at ?? row.timestamp)}`,
          },
          {
            label: "Battery",
            value: Number.isFinite(batteryPercent)
              ? `${Math.round(batteryPercent)}% · ${batteryStatus}`
              : `Unknown · ${batteryStatus}`,
          },
          {
            label: "Battery source",
            value: unknown(bluetooth?.battery?.source),
          },
        ]
      : [];
    return {
      title: `Object ${unknown(row.id ?? selection.id)}`,
      kind: fusion
        ? "Vision + Bluetooth fused object"
        : bluetooth
          ? "Bluetooth tracked object"
          : "Tracked object",
      fields: [
        { label: "Category", value: unknown(row.category ?? row.type) },
        { label: "Position", value: vector(row.translation) },
        { label: "Velocity", value: vector(row.velocity) },
        { label: "Speed", value: speed === "Unknown" ? speed : `${speed} m/s` },
        ...fusionFields,
        ...bluetoothFields,
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
