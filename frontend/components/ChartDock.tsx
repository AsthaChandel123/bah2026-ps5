"use client";

import dynamic from "next/dynamic";
import { useStore, baseVariableOf } from "@/lib/store";

// Charts are client-only (Canvas / window). Dynamic-import to keep them out of SSR.
const PointTimeSeries = dynamic(() => import("@/components/PointTimeSeries"), {
  ssr: false,
});
const ClimatologyPanel = dynamic(() => import("@/components/ClimatologyPanel"), {
  ssr: false,
});
const ForecastPanel = dynamic(() => import("@/components/ForecastPanel"), {
  ssr: false,
});

export default function ChartDock() {
  const variable = useStore((s) => s.variable);
  const selectedCell = useStore((s) => s.selectedCell);
  const setSelectedCell = useStore((s) => s.setSelectedCell);
  const forecast = useStore((s) => s.forecast);
  const showForecast = useStore((s) => s.showForecast);
  const toggleForecast = useStore((s) => s.toggleForecast);
  const baseVar = baseVariableOf(variable);
  const label =
    baseVar === "rainfall" ? "Rainfall" : baseVar === "tmax" ? "Max Temp" : "Min Temp";

  return (
    <div className="chartdock">
      <div className="panel chart-card">
        <div className="chart-head">
          <span className="ttl">Point time series · {label}</span>
          {selectedCell && (
            <button
              className="btn ghost"
              style={{ padding: "3px 8px", fontSize: 10 }}
              onClick={() => setSelectedCell(null)}
            >
              clear
            </button>
          )}
        </div>
        <PointTimeSeries />
      </div>

      {/* 7-Day forecast: only offered when the artifact loaded. Toggleable so it
          doesn't crowd the dock by default. */}
      {forecast &&
        (showForecast ? (
          <div className="panel chart-card">
            <div className="chart-head">
              <span className="ttl">
                {forecast.leads.length}-day forecast · {label}
              </span>
              <button
                className="btn ghost"
                style={{ padding: "3px 8px", fontSize: 10 }}
                onClick={toggleForecast}
              >
                hide
              </button>
            </div>
            <ForecastPanel />
          </div>
        ) : (
          <button
            className="btn ghost forecast-toggle"
            style={{ alignSelf: "flex-start", padding: "5px 10px", fontSize: 11 }}
            onClick={toggleForecast}
          >
            ▸ Show {forecast.leads.length}-day forecast
          </button>
        ))}

      <div className="panel chart-card">
        <div className="chart-head">
          <span className="ttl">Monthly climatology · {label}</span>
          <span className="meta">{selectedCell ? "region + cell" : "region"}</span>
        </div>
        <ClimatologyPanel />
      </div>
    </div>
  );
}
