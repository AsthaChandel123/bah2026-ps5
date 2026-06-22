"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useStore, baseVariableOf } from "@/lib/store";
import {
  computeImpactSummary,
  physicsFromScenarios,
  isBaseline,
  type ImpactSummary,
} from "@/lib/whatif";
import type { ScenarioState, ScenarioControl } from "@/lib/types";

/** Default control specs if scenarios.json is missing. */
const DEFAULT_CONTROLS: Record<keyof ScenarioState, ScenarioControl> = {
  temp_offset: { label: "Temperature change", unit: "°C", min: -2, max: 5, step: 0.5, default: 0 },
  rain_pct: { label: "Rainfall change", unit: "%", min: -50, max: 50, step: 5, default: 0 },
  onset_shift: { label: "Monsoon onset shift", unit: "days", min: -20, max: 20, step: 1, default: 0 },
};

function fmtSigned(v: number, digits = 0) {
  const s = v.toFixed(digits);
  return v > 0 ? `+${s}` : s;
}

export default function WhatIfPanel() {
  const fields = useStore((s) => s.fields);
  const scenarios = useStore((s) => s.scenarios);
  const variable = useStore((s) => s.variable);
  const scenario = useStore((s) => s.scenario);
  const applyScenario = useStore((s) => s.applyScenario);
  const resetScenario = useStore((s) => s.resetScenario);
  const comparing = useStore((s) => s.comparing);
  const setComparing = useStore((s) => s.setComparing);

  const baseVar = baseVariableOf(variable);
  const phys = useMemo(() => physicsFromScenarios(scenarios), [scenarios]);
  const controls = scenarios?.controls ?? DEFAULT_CONTROLS;
  const presets = scenarios?.presets ?? [];

  // Local (immediate) slider state for buttery dragging; committed to the
  // store on a debounce so the map/charts recompute only when the drag settles.
  const [draft, setDraft] = useState<ScenarioState>(scenario);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // keep draft in sync when scenario changes externally (presets / reset)
  useEffect(() => {
    setDraft(scenario);
  }, [scenario]);

  const commitDebounced = (next: ScenarioState) => {
    setDraft(next);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => applyScenario(next), 180);
  };

  const onSlider = (key: keyof ScenarioState, value: number) => {
    commitDebounced({ ...draft, [key]: value });
  };

  // Impact summary computed from the COMMITTED scenario (not draft) so it
  // reflects the displayed field; recompute only when scenario/variable change.
  const impact: ImpactSummary | null = useMemo(() => {
    if (!fields) return null;
    return computeImpactSummary(fields, baseVar, scenario, phys);
  }, [fields, baseVar, scenario, phys]);

  const sliderFill = (c: ScenarioControl, v: number) =>
    `${((v - c.min) / (c.max - c.min)) * 100}%`;

  const applyPreset = (p: { temp_offset: number; rain_pct: number; onset_shift: number }) => {
    const next: ScenarioState = {
      temp_offset: p.temp_offset,
      rain_pct: p.rain_pct,
      onset_shift: p.onset_shift,
    };
    applyScenario(next);
  };

  const baselineActive = isBaseline(scenario);

  return (
    <>
      <div className="panel card">
        <div className="panel-title">What-If Scenario Engine</div>

        {(["temp_offset", "rain_pct", "onset_shift"] as const).map((key) => {
          const c = controls[key];
          const v = draft[key];
          return (
            <div className="slider-block" key={key}>
              <div className="slider-head">
                <span className="lab">{c.label}</span>
                <span className="val">
                  {fmtSigned(v, key === "temp_offset" ? 1 : 0)} {c.unit}
                </span>
              </div>
              <input
                type="range"
                min={c.min}
                max={c.max}
                step={c.step}
                value={v}
                style={{ ["--fill" as string]: sliderFill(c, v) }}
                onChange={(e) => onSlider(key, parseFloat(e.target.value))}
              />
            </div>
          );
        })}

        <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
          <button
            className="btn"
            style={{ flex: 1 }}
            onClick={resetScenario}
            disabled={baselineActive}
          >
            Reset to baseline
          </button>
          <button
            className={`btn ${comparing ? "active" : ""}`}
            style={{ flex: 1 }}
            onClick={() => setComparing(!comparing)}
            disabled={variable === "uncertainty"}
          >
            {comparing ? "Comparing" : "Compare"}
          </button>
        </div>
      </div>

      <div className="panel card">
        <div className="panel-title">Preset Scenarios</div>
        <div className="preset-grid">
          {presets.map((p) => {
            const active =
              scenario.temp_offset === p.temp_offset &&
              scenario.rain_pct === p.rain_pct &&
              scenario.onset_shift === p.onset_shift;
            return (
              <button
                key={p.id}
                className={`btn ${active ? "active" : ""}`}
                onClick={() => applyPreset(p)}
              >
                {p.label}
              </button>
            );
          })}
          {presets.length === 0 && (
            <div className="help-line">No presets in scenarios.json.</div>
          )}
        </div>
      </div>

      <div className="panel card">
        <div className="panel-title">
          Impact Summary · {baseVar === "rainfall" ? "Rainfall" : baseVar === "tmax" ? "Max Temp" : "Min Temp"}
        </div>
        {impact ? (
          baseVar === "rainfall" ? (
            <div className="impact">
              <Metric
                k="Δ Seasonal rain"
                v={`${fmtSigned(impact.deltaSeasonalRain ?? 0, 0)} mm`}
                sub={`${fmtSigned(impact.deltaSeasonalRainPct ?? 0, 1)}%`}
                dir={signDir(impact.deltaSeasonalRain ?? 0, true)}
              />
              <Metric
                k="Δ Extreme-rain days"
                v={fmtSigned(impact.deltaExtremeDays ?? 0, 1)}
                sub={`>p${phys.heavyRainPercentile} days`}
                dir={signDir(impact.deltaExtremeDays ?? 0, false)}
              />
              <Metric
                k="Baseline total"
                v={`${(impact.baselineSeasonalRain ?? 0).toFixed(0)} mm`}
                sub="region mean / yr"
                dir="neutral"
              />
              <Metric
                k="Scenario total"
                v={`${(impact.scenarioSeasonalRain ?? 0).toFixed(0)} mm`}
                sub="region mean / yr"
                dir="neutral"
              />
            </div>
          ) : (
            <div className="impact">
              <Metric
                k="Δ Mean temp"
                v={`${fmtSigned(impact.deltaMeanTemp ?? 0, 1)} °C`}
                sub="uniform ΔT"
                dir={signDir(impact.deltaMeanTemp ?? 0, false)}
              />
              <Metric
                k="Baseline mean"
                v={`${(impact.baselineMeanTemp ?? 0).toFixed(1)} °C`}
                sub="annual region mean"
                dir="neutral"
              />
              <Metric
                k="Scenario mean"
                v={`${(impact.scenarioMeanTemp ?? 0).toFixed(1)} °C`}
                sub="annual region mean"
                dir="neutral"
              />
              <Metric
                k="CC effect"
                v={`${phys.ccPctPerDegC}%/°C`}
                sub="on heavy rain"
                dir="neutral"
              />
            </div>
          )
        ) : (
          <div className="help-line">Computing…</div>
        )}
        <div className="help-line" style={{ marginTop: 10 }}>
          Heavy-rain (&gt;p{phys.heavyRainPercentile}) days are intensified by
          Clausius&ndash;Clapeyron ({phys.ccPctPerDegC}%/°C) under warming.
          Onset shift rolls the rainfall time axis.
        </div>
      </div>
    </>
  );
}

function signDir(v: number, invertGood: boolean): "up" | "down" | "neutral" {
  if (Math.abs(v) < 1e-6) return "neutral";
  // For rainfall total, "down" (less rain) is the concerning direction for a
  // drought belt, but we color by sign neutrally: increases red, decreases cyan.
  void invertGood;
  return v > 0 ? "up" : "down";
}

function Metric({
  k,
  v,
  sub,
  dir,
}: {
  k: string;
  v: string;
  sub?: string;
  dir: "up" | "down" | "neutral";
}) {
  const cls =
    dir === "up" ? "delta-up" : dir === "down" ? "delta-down" : "delta-neutral";
  return (
    <div className="metric">
      <div className="k">{k}</div>
      <div className={`v ${cls}`}>{v}</div>
      {sub && (
        <div style={{ fontSize: 10, color: "var(--text-2)", marginTop: 2 }}>
          {sub}
        </div>
      )}
    </div>
  );
}
