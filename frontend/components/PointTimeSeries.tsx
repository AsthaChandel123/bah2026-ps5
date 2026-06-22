"use client";

import { useEffect, useMemo, useRef } from "react";
import uPlot from "uplot";
import { useStore, baseVariableOf } from "@/lib/store";
import {
  scenarioSeriesAtCell,
  physicsFromScenarios,
  isBaseline,
} from "@/lib/whatif";

/**
 * Fast click-a-point time-series (uPlot, Canvas 2D). Shows the selected cell's
 * full-year series for the active base variable; overlays the scenario series
 * when a non-baseline scenario is active. Redraws instantly on scrub / what-if.
 */
export default function PointTimeSeries() {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const plotRef = useRef<uPlot | null>(null);
  const widthRef = useRef<number>(340);

  const fields = useStore((s) => s.fields);
  const metadata = useStore((s) => s.metadata);
  const scenarios = useStore((s) => s.scenarios);
  const variable = useStore((s) => s.variable);
  const scenario = useStore((s) => s.scenario);
  const selectedCell = useStore((s) => s.selectedCell);
  const timeIndex = useStore((s) => s.timeIndex);

  const baseVar = baseVariableOf(variable);
  const phys = useMemo(() => physicsFromScenarios(scenarios), [scenarios]);
  const hasScenario = !isBaseline(scenario);

  // Build the uPlot data array [x, baseline, scenario?]
  const data = useMemo<uPlot.AlignedData | null>(() => {
    if (!fields || !metadata || !selectedCell) return null;
    const xs = metadata.time.dates.map((d) => Date.parse(d) / 1000);
    const { baseline, scenario: scen } = scenarioSeriesAtCell(
      fields,
      baseVar,
      selectedCell.i,
      selectedCell.j,
      scenario,
      phys
    );
    if (hasScenario) {
      return [xs, baseline, scen] as uPlot.AlignedData;
    }
    return [xs, baseline] as uPlot.AlignedData;
  }, [fields, metadata, selectedCell, baseVar, scenario, phys, hasScenario]);

  const units = metadata?.variables[baseVar].units ?? "";
  const isRain = baseVar === "rainfall";

  // (Re)create the plot when series shape (number of series) changes.
  useEffect(() => {
    if (!hostRef.current || !data) {
      // destroy if no data
      if (plotRef.current) {
        plotRef.current.destroy();
        plotRef.current = null;
      }
      return;
    }
    const width = hostRef.current.clientWidth || widthRef.current;
    widthRef.current = width;

    const baseColor = isRain ? "#6baed6" : "#f46d43";
    const scenColor = "#ffb347";

    const series: uPlot.Series[] = [
      {},
      {
        label: "Baseline",
        stroke: baseColor,
        width: 1.5,
        fill: isRain ? "rgba(107,174,214,0.18)" : "rgba(244,109,67,0.12)",
        points: { show: false },
      },
    ];
    if (hasScenario) {
      series.push({
        label: "Scenario",
        stroke: scenColor,
        width: 1.5,
        dash: [4, 3],
        points: { show: false },
      });
    }

    const opts: uPlot.Options = {
      width,
      height: 150,
      padding: [8, 8, 0, 0],
      series,
      cursor: { y: false, points: { size: 6 } },
      legend: { show: true, live: true },
      scales: { x: { time: true }, y: { auto: true } },
      axes: [
        {
          stroke: "#6b7c93",
          grid: { stroke: "rgba(120,160,210,0.08)" },
          ticks: { stroke: "rgba(120,160,210,0.15)" },
          font: "10px ui-monospace, monospace",
          values: (_u, splits) =>
            splits.map((s) => {
              const d = new Date(s * 1000);
              return d.toLocaleDateString("en", { month: "short" });
            }),
        },
        {
          stroke: "#6b7c93",
          grid: { stroke: "rgba(120,160,210,0.08)" },
          ticks: { stroke: "rgba(120,160,210,0.15)" },
          font: "10px ui-monospace, monospace",
          size: 38,
        },
      ],
    };

    // recreate
    if (plotRef.current) {
      plotRef.current.destroy();
      plotRef.current = null;
    }
    plotRef.current = new uPlot(opts, data, hostRef.current);

    return () => {
      if (plotRef.current) {
        plotRef.current.destroy();
        plotRef.current = null;
      }
    };
    // recreate when the number of series or variable changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasScenario, isRain, baseVar, !!data && !!selectedCell]);

  // Fast path: update data in-place when only values change.
  useEffect(() => {
    if (plotRef.current && data) {
      plotRef.current.setData(data);
    }
  }, [data]);

  // Resize handling
  useEffect(() => {
    const onResize = () => {
      if (plotRef.current && hostRef.current) {
        plotRef.current.setSize({
          width: hostRef.current.clientWidth || widthRef.current,
          height: 150,
        });
      }
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  if (!selectedCell) {
    return (
      <div className="empty-hint">
        Click a cell on the map to plot its yearly {isRain ? "rainfall" : "temperature"} series.
      </div>
    );
  }

  const currentVal =
    fields && selectedCell
      ? fields[baseVar][timeIndex][selectedCell.i][selectedCell.j]
      : null;

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 10,
          color: "var(--text-2)",
          marginBottom: 4,
        }}
      >
        <span className="kbd">
          {selectedCell.lat.toFixed(2)}°N {selectedCell.lon.toFixed(2)}°E
        </span>
        {currentVal != null && (
          <span style={{ fontFamily: "var(--mono)" }}>
            today: {currentVal.toFixed(isRain ? 1 : 1)} {units}
          </span>
        )}
      </div>
      <div ref={hostRef} className="uplot-host" />
    </div>
  );
}
