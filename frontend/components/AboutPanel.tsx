"use client";

import { useStore } from "@/lib/store";
import { dataApi } from "@/lib/api";

export default function AboutPanel() {
  const metadata = useStore((s) => s.metadata);

  return (
    <div style={{ lineHeight: 1.6, color: "var(--text-1)", fontSize: 13 }}>
      <h3 style={{ color: "var(--text-0)", marginBottom: 8 }}>
        Bharat Climate Twin
      </h3>
      <p style={{ marginTop: 0 }}>
        A <strong>dynamic virtual replica</strong> of India&rsquo;s climate
        system (rainfall + temperature), focused for this PoC on the{" "}
        <strong>Marathwada</strong> drought belt. It is a <em>twin</em>, not a
        dashboard, because it does three things at once:
      </p>
      <ol style={{ paddingLeft: 20 }}>
        <li>
          <strong>Tracks reality</strong> via two-stage Bayesian{" "}
          <em>data assimilation</em> that fuses 30+ cross-validating satellite,
          reanalysis and gauge sources onto the IMD ground-truth anchor &mdash;
          with a <strong>per-pixel uncertainty field</strong>.
        </li>
        <li>
          <strong>Evolves &amp; predicts</strong> through an AI/ML ensemble
          (XGBoost/LightGBM + ConvLSTM + U-Net downscaler + SARIMAX/Analog,
          fused by stacking + EMOS + conformal calibration).
        </li>
        <li>
          <strong>Is perturbable</strong> through this{" "}
          <em>what-if engine</em>: ΔTemperature, ΔRainfall and monsoon-onset
          shifts recompute the field <strong>in real time on your GPU/CPU</strong>,
          with Clausius&ndash;Clapeyron intensification of heavy-rain extremes.
        </li>
      </ol>

      <h4 style={{ color: "var(--text-0)", marginTop: 18 }}>How to use</h4>
      <ul style={{ paddingLeft: 20 }}>
        <li>Pick a layer (Rainfall / Tmax / Tmin / Uncertainty) in the left rail.</li>
        <li>Press the timeline play button (or <span className="kbd">Space</span>) to animate the year.</li>
        <li>Click any cell to chart its yearly series + monthly climatology.</li>
        <li>Open <strong>What-If Engine</strong>, drag the sliders or pick a preset, and watch the map + charts update live.</li>
        <li>Toggle <strong>Compare</strong> and drag the swipe handle for a baseline-vs-scenario split.</li>
      </ul>

      <h4 style={{ color: "var(--text-0)", marginTop: 18 }}>Stack</h4>
      <p style={{ marginTop: 0 }}>
        Next.js + React + TypeScript · MapLibre GL JS (open, not Mapbox) ·
        deck.gl (interleaved GPU overlay) · uPlot + ECharts · Zustand. Designed
        for O(1) edge serving: the field is tiny and lives in the browser, so
        animation and what-if are instant.
      </p>

      <div
        className="panel"
        style={{ padding: 12, marginTop: 16, background: "var(--bg-1)" }}
      >
        <div className="panel-title">Current dataset</div>
        {metadata ? (
          <div style={{ fontSize: 12, fontFamily: "var(--mono)", color: "var(--text-1)" }}>
            region: {metadata.region_label ?? metadata.region}
            <br />
            bbox: [{metadata.bbox.join(", ")}] ({metadata.crs})
            <br />
            grid: {metadata.grid.nlat}×{metadata.grid.nlon} @ {metadata.grid.res_deg}°
            <br />
            time: {metadata.time.start} → {metadata.time.end} ({metadata.time.n} days)
            <br />
            source: {dataApi.base}
            {metadata.generator?.includes("sample") && (
              <>
                <br />
                <span style={{ color: "var(--accent-warm)" }}>
                  ⚠ synthetic sample data (real artifacts use the same schema)
                </span>
              </>
            )}
          </div>
        ) : (
          <div className="help-line">No metadata loaded.</div>
        )}
      </div>

      <p className="help-line" style={{ marginTop: 16 }}>
        ISRO Bharatiya Antariksh Hackathon (BAH) 2026 · Problem Statement 5.
        Indigenous, open, free-tier-feasible &mdash; scales cleanly from the
        Marathwada pilot to a national digital twin of India&rsquo;s climate.
      </p>
    </div>
  );
}
