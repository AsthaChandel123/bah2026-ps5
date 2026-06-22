"use client";

import { useStore } from "@/lib/store";
import type { VariableKey } from "@/lib/types";

const LAYERS: { id: VariableKey; label: string; hint: string }[] = [
  { id: "rainfall", label: "Rainfall", hint: "mm/day" },
  { id: "tmax", label: "Max Temp", hint: "°C" },
  { id: "tmin", label: "Min Temp", hint: "°C" },
  { id: "uncertainty", label: "Uncertainty", hint: "1σ" },
];

export default function LayerPanel() {
  const variable = useStore((s) => s.variable);
  const setVariable = useStore((s) => s.setVariable);
  const opacity = useStore((s) => s.opacity);
  const setOpacity = useStore((s) => s.setOpacity);
  const comparing = useStore((s) => s.comparing);
  const toggleComparing = useStore((s) => s.toggleComparing);
  const metadata = useStore((s) => s.metadata);

  return (
    <div className="panel card">
      <div className="panel-title">Climate Layer</div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 6,
          marginBottom: 16,
        }}
      >
        {LAYERS.map((l) => (
          <button
            key={l.id}
            className={`btn ${variable === l.id ? "active" : ""}`}
            onClick={() => setVariable(l.id)}
            style={{ textAlign: "left" }}
          >
            <div style={{ fontWeight: 600 }}>{l.label}</div>
            <div style={{ fontSize: 10, color: "var(--text-2)" }}>{l.hint}</div>
          </button>
        ))}
      </div>

      <div className="slider-block">
        <div className="slider-head">
          <span className="lab">Layer opacity</span>
          <span className="val">{Math.round(opacity * 100)}%</span>
        </div>
        <input
          type="range"
          min={0.15}
          max={1}
          step={0.05}
          value={opacity}
          style={{ ["--fill" as string]: `${((opacity - 0.15) / 0.85) * 100}%` }}
          onChange={(e) => setOpacity(parseFloat(e.target.value))}
        />
      </div>

      <div className="field-row" style={{ marginTop: 4 }}>
        <span className="field-label">Before / after compare</span>
        <button
          className={`btn ${comparing ? "active" : ""}`}
          onClick={toggleComparing}
          disabled={variable === "uncertainty"}
          title={
            variable === "uncertainty"
              ? "Compare applies to rainfall/temperature scenarios"
              : "Swipe to compare baseline vs scenario"
          }
        >
          {comparing ? "On" : "Off"}
        </button>
      </div>

      <div
        className="help-line"
        style={{ marginTop: 12, borderTop: "1px solid var(--border)", paddingTop: 10 }}
      >
        Click any cell on the map to chart its yearly series + climatology.
        <br />
        <span className="kbd">Space</span> play/pause &nbsp;
        <span className="kbd">←</span>/<span className="kbd">→</span> step day.
        {metadata && (
          <>
            <br />
            <span style={{ color: "var(--text-2)" }}>
              Grid {metadata.grid.nlat}×{metadata.grid.nlon} @{" "}
              {metadata.grid.res_deg}° · {metadata.time.n} days
            </span>
          </>
        )}
      </div>
    </div>
  );
}
