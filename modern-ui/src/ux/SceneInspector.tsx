import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";
import { buildInspectorModel, refreshObjectSelection } from "./sceneInspector";
import type { SceneSelection } from "./sceneInspector";

type Row = Record<string, any>;

export default function SceneInspector({
  selection,
  liveObjects,
  collapsed,
  onToggleCollapse,
  onClear,
}: {
  selection: SceneSelection;
  liveObjects: Row[];
  collapsed: boolean;
  onToggleCollapse: () => void;
  onClear: () => void;
}) {
  const [cameraTelemetry, setCameraTelemetry] = useState<Row | null>(null);
  const [sensorTelemetry, setSensorTelemetry] = useState<Row[] | null>(null);
  const currentSelection = refreshObjectSelection(selection, liveObjects);

  useEffect(() => {
    let active = true;
    let timer = 0;
    setCameraTelemetry(null);
    setSensorTelemetry(null);
    const refresh = () => {
      if (!selection) return;
      if (selection.kind === "camera") {
        void apiFetch<Row>(
          `/api/v2/cameras/${encodeURIComponent(selection.id)}/telemetry`,
        )
          .then((value) => {
            if (active) setCameraTelemetry(value);
          })
          .catch(() => {});
      } else if (selection.kind === "sensor") {
        void apiFetch<Row[]>(
          `/api/v2/sensors/${encodeURIComponent(selection.id)}/telemetry?limit=1`,
        )
          .then((value) => {
            if (active) setSensorTelemetry(value);
          })
          .catch(() => {});
      }
    };
    if (selection?.kind === "camera" || selection?.kind === "sensor") {
      refresh();
      timer = window.setInterval(refresh, 3000);
    }
    return () => {
      active = false;
      if (timer) window.clearInterval(timer);
    };
  }, [selection?.kind, selection?.id]);

  if (collapsed) {
    return (
      <aside className="scene-inspector collapsed" aria-label="Scene inspector">
        <button className="scene-inspector-expand" onClick={onToggleCollapse}>
          Inspector ›
        </button>
      </aside>
    );
  }

  const model = buildInspectorModel(currentSelection, {
    cameraTelemetry,
    sensorTelemetry,
  });
  if (!model) {
    return (
      <aside className="scene-inspector empty" aria-label="Scene inspector">
        <div className="scene-inspector-empty-state">
          <b>Inspector</b>
          <span>Select an object, camera, sensor, region, or tripwire.</span>
        </div>
      </aside>
    );
  }

  return (
    <aside className="scene-inspector" aria-label="Scene inspector">
      <header className="scene-inspector-header">
        <div>
          <span>{model.kind}</span>
          <h2>{model.title}</h2>
        </div>
        <div className="scene-inspector-actions">
          <button
            className="text-button"
            onClick={onToggleCollapse}
            aria-label="Collapse inspector"
          >
            Collapse
          </button>
          <button className="text-button" onClick={onClear}>
            Clear
          </button>
        </div>
      </header>
      <dl className="scene-inspector-fields">
        {model.fields.map((field) => (
          <div key={field.label}>
            <dt>{field.label}</dt>
            <dd>{field.value}</dd>
          </div>
        ))}
      </dl>
      {model.persistentData && (
        <section className="scene-inspector-persistent">
          <h3>Persistent data</h3>
          <pre>{model.persistentData}</pre>
        </section>
      )}
    </aside>
  );
}
