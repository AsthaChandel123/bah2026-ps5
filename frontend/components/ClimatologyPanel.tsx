"use client";

import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { useStore, baseVariableOf } from "@/lib/store";

const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

/**
 * Monthly climatology (ECharts). Shows the region-mean monthly climatology for
 * the active base variable, plus the SELECTED cell's own monthly means computed
 * on the fly from the daily cube (so click-a-point also drives this panel).
 */
export default function ClimatologyPanel() {
  const climatology = useStore((s) => s.climatology);
  const fields = useStore((s) => s.fields);
  const metadata = useStore((s) => s.metadata);
  const variable = useStore((s) => s.variable);
  const selectedCell = useStore((s) => s.selectedCell);
  const baseVar = baseVariableOf(variable);
  const isRain = baseVar === "rainfall";

  // Per-cell monthly aggregate (sum for rain, mean for temp).
  const cellMonthly = useMemo<number[] | null>(() => {
    if (!fields || !metadata || !selectedCell) return null;
    const sums = new Array(12).fill(0);
    const counts = new Array(12).fill(0);
    const dates = metadata.time.dates;
    for (let t = 0; t < dates.length; t++) {
      const m = new Date(dates[t] + "T00:00:00Z").getUTCMonth();
      sums[m] += fields[baseVar][t][selectedCell.i][selectedCell.j];
      counts[m] += 1;
    }
    return sums.map((s, m) => (isRain ? s : counts[m] ? s / counts[m] : 0));
  }, [fields, metadata, selectedCell, baseVar, isRain]);

  const regionMonthly = climatology?.region_mean?.[baseVar] ?? null;

  const option = useMemo(() => {
    const color = isRain ? "#6baed6" : "#f46d43";
    const series: Record<string, unknown>[] = [];
    if (regionMonthly) {
      series.push({
        name: "Region mean",
        type: isRain ? "bar" : "line",
        data: regionMonthly,
        itemStyle: { color },
        smooth: !isRain,
        symbol: "none",
        lineStyle: { width: 2 },
        z: 1,
      });
    }
    if (cellMonthly) {
      series.push({
        name: "Selected cell",
        type: "line",
        data: cellMonthly,
        itemStyle: { color: "#36c5f0" },
        lineStyle: { width: 2, type: "dashed" },
        symbol: "circle",
        symbolSize: 5,
        z: 2,
      });
    }
    return {
      grid: { left: 36, right: 10, top: 24, bottom: 22 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#0c131d",
        borderColor: "rgba(120,160,210,0.28)",
        textStyle: { color: "#e8eef7", fontSize: 11 },
      },
      legend: {
        show: series.length > 1,
        top: 0,
        right: 0,
        textStyle: { color: "#aab8cc", fontSize: 10 },
        itemWidth: 14,
        itemHeight: 8,
      },
      xAxis: {
        type: "category",
        data: MONTHS,
        axisLine: { lineStyle: { color: "rgba(120,160,210,0.25)" } },
        axisLabel: { color: "#6b7c93", fontSize: 10 },
        axisTick: { show: false },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "rgba(120,160,210,0.08)" } },
        axisLabel: { color: "#6b7c93", fontSize: 10 },
        name: isRain ? "mm" : "°C",
        nameTextStyle: { color: "#6b7c93", fontSize: 9 },
      },
      series,
    };
  }, [regionMonthly, cellMonthly, isRain]);

  if (!regionMonthly && !cellMonthly) {
    return (
      <div className="empty-hint">
        Climatology unavailable.
        <br />
        (Add climatology.json or click a cell.)
      </div>
    );
  }

  return (
    <ReactECharts
      option={option}
      style={{ height: 168, width: "100%" }}
      notMerge
      lazyUpdate
      opts={{ renderer: "canvas" }}
    />
  );
}
