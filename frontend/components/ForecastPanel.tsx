"use client";

import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useStore, baseVariableOf } from "@/lib/store";
import type { BaseVariableKey } from "@/lib/types";

/**
 * 7-Day AI Forecast (ECharts) for the selected grid cell.
 *
 * Reads the forecast frame (`/data/forecast.json`, or `/api/forecast` when
 * NEXT_PUBLIC_API_BASE is set — see lib/api.ts) which is indexed
 * `[lead][lat][lon]` for rainfall / tmax / tmin, plus a matching `uncertainty`
 * (1-sigma, absolute units). For the active base variable we plot the lead-1..7
 * mean line with a ±1σ uncertainty band (the standard ECharts stacked-area band
 * trick: an invisible lower baseline + a translucent band of height 2σ).
 */

/** Nearest index into a coordinate array. */
function nearestIdx(coords: number[] | undefined, target: number): number {
  if (!coords || coords.length === 0) return 0;
  let best = 0;
  let bestD = Infinity;
  for (let k = 0; k < coords.length; k++) {
    const d = Math.abs(coords[k] - target);
    if (d < bestD) {
      bestD = d;
      best = k;
    }
  }
  return best;
}

export default function ForecastPanel() {
  const forecast = useStore((s) => s.forecast);
  const selectedCell = useStore((s) => s.selectedCell);
  const variable = useStore((s) => s.variable);
  const baseVar: BaseVariableKey = baseVariableOf(variable);
  const isRain = baseVar === "rainfall";

  // Resolve the cell within the forecast grid (same 0.25° lattice as the cube,
  // but resolve by lat/lon to be robust if the producer reorders coords).
  const series = useMemo(() => {
    if (!forecast || !selectedCell) return null;
    const i = nearestIdx(forecast.lats, selectedCell.lat);
    const j = nearestIdx(forecast.lons, selectedCell.lon);
    const vals = forecast[baseVar];
    const unc = forecast.uncertainty?.[baseVar];
    if (!vals) return null;

    const mean: number[] = [];
    const lower: number[] = [];
    const bandHeight: number[] = []; // 2σ, stacked on top of `lower`
    for (let l = 0; l < forecast.leads.length; l++) {
      const v = vals[l]?.[i]?.[j];
      if (typeof v !== "number") {
        mean.push(NaN);
        lower.push(NaN);
        bandHeight.push(NaN);
        continue;
      }
      const sigma = unc?.[l]?.[i]?.[j] ?? 0;
      let lo = v - sigma;
      if (isRain && lo < 0) lo = 0; // rainfall can't be negative
      mean.push(Number(v.toFixed(isRain ? 1 : 2)));
      lower.push(Number(lo.toFixed(isRain ? 1 : 2)));
      bandHeight.push(Number((v + sigma - lo).toFixed(isRain ? 1 : 2)));
    }
    return { mean, lower, bandHeight, i, j };
  }, [forecast, selectedCell, baseVar, isRain]);

  const option = useMemo(() => {
    if (!forecast || !series) return {};
    const color = isRain ? "#6baed6" : "#f46d43";
    const units = forecast.units?.[baseVar] ?? (isRain ? "mm/day" : "°C");
    // x labels: short day-of-week + day for the forecast dates.
    const labels = forecast.dates.map((d, k) => {
      const dt = new Date(d + "T00:00:00Z");
      const dow = dt.toLocaleDateString("en", {
        weekday: "short",
        timeZone: "UTC",
      });
      return `${dow}\n+${forecast.leads[k]}d`;
    });

    return {
      grid: { left: 38, right: 10, top: 24, bottom: 28 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#0c131d",
        borderColor: "rgba(120,160,210,0.28)",
        textStyle: { color: "#e8eef7", fontSize: 11 },
        formatter: (params: unknown) => {
          const arr = params as Array<{
            axisValue: string;
            dataIndex: number;
          }>;
          if (!arr || !arr.length) return "";
          const k = arr[0].dataIndex;
          const m = series.mean[k];
          const lo = series.lower[k];
          const hi = lo + series.bandHeight[k];
          const date = forecast.dates[k];
          return (
            `${date} (lead +${forecast.leads[k]}d)<br/>` +
            `${baseVar}: <b>${m}</b> ${units}<br/>` +
            `±1σ: ${lo} – ${hi.toFixed(isRain ? 1 : 2)} ${units}`
          );
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: "rgba(120,160,210,0.25)" } },
        axisLabel: { color: "#6b7c93", fontSize: 9, lineHeight: 11 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        scale: !isRain,
        splitLine: { lineStyle: { color: "rgba(120,160,210,0.08)" } },
        axisLabel: { color: "#6b7c93", fontSize: 10 },
        name: units,
        nameTextStyle: { color: "#6b7c93", fontSize: 9 },
      },
      series: [
        // Invisible lower baseline for the band.
        {
          name: "lo",
          type: "line",
          data: series.lower,
          stack: "band",
          lineStyle: { opacity: 0 },
          symbol: "none",
          silent: true,
          z: 1,
        },
        // Visible band (height = 2σ) stacked on the baseline.
        {
          name: "±1σ",
          type: "line",
          data: series.bandHeight,
          stack: "band",
          lineStyle: { opacity: 0 },
          areaStyle: { color, opacity: 0.16 },
          symbol: "none",
          silent: true,
          z: 1,
        },
        // The mean forecast line.
        {
          name: "forecast",
          type: "line",
          data: series.mean,
          itemStyle: { color },
          lineStyle: { width: 2, color },
          symbol: "circle",
          symbolSize: 5,
          z: 3,
        },
      ],
    };
  }, [forecast, series, baseVar, isRain]);

  if (!forecast) {
    return (
      <div className="empty-hint">
        No forecast available.
        <br />
        models/train.py writes data/forecast.json (lead-1..7); the backend serves
        it at <span className="kbd">/api/forecast</span>.
      </div>
    );
  }

  if (!selectedCell || !series) {
    return (
      <div className="empty-hint">
        Click a cell on the map to see its {forecast.leads.length}-day{" "}
        {isRain ? "rainfall" : "temperature"} forecast with the uncertainty band.
      </div>
    );
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 10,
          color: "var(--text-2)",
          marginBottom: 2,
        }}
      >
        <span className="kbd">
          {selectedCell.lat.toFixed(2)}°N {selectedCell.lon.toFixed(2)}°E
        </span>
        <span style={{ fontFamily: "var(--mono)" }}>
          issued {forecast.issue_date}
        </span>
      </div>
      <ReactECharts
        option={option}
        style={{ height: 168, width: "100%" }}
        notMerge
        lazyUpdate
        opts={{ renderer: "canvas" }}
      />
    </div>
  );
}
