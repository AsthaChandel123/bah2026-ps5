// What-if scenario engine — client-side recompute of the displayed field.
//
// Implements the contract physics (ARCHITECTURE §8):
//   tmax' = tmax + ΔT
//   tmin' = tmin + ΔT
//   rainfall' = rainfall * (1 + ΔP/100)
//     + heavy-rain (>p90) days additionally amplified by
//       (clausius_clapeyron_pct_per_degC / 100) * ΔT     (Clausius–Clapeyron)
//   onset_shift: roll the rainfall TIME axis by N days
//
// Everything operates on the tiny in-browser cube, so applying a scenario to a
// single timestep (for the map) or a single cell's full series (for the charts)
// is effectively instant. Slider drags are debounced upstream.

import type {
  BaseVariableKey,
  FieldsDaily,
  ScenarioState,
  Scenarios,
} from "./types";

export interface WhatIfPhysics {
  ccPctPerDegC: number; // Clausius–Clapeyron %/°C
  heavyRainPercentile: number; // p-threshold for "heavy rain" days
}

export function physicsFromScenarios(s: Scenarios | null): WhatIfPhysics {
  return {
    ccPctPerDegC: s?.physics?.clausius_clapeyron_pct_per_degC ?? 7,
    heavyRainPercentile: s?.physics?.heavy_rain_percentile ?? 90,
  };
}

export function isBaseline(sc: ScenarioState): boolean {
  return sc.temp_offset === 0 && sc.rain_pct === 0 && sc.onset_shift === 0;
}

/** Positive modulo so onset rolls wrap correctly for negative shifts. */
function mod(n: number, m: number): number {
  return ((n % m) + m) % m;
}

/**
 * Per-cell heavy-rain threshold (p90 over the year for that cell), computed
 * from the BASELINE cube. Cached on the fields object so we only compute once.
 */
const P90_CACHE = new WeakMap<FieldsDaily, { pct: number; grid: number[][] }>();

export function heavyRainThresholdGrid(
  fields: FieldsDaily,
  percentile: number
): number[][] {
  const cached = P90_CACHE.get(fields);
  if (cached && cached.pct === percentile) return cached.grid;

  const nT = fields.rainfall.length;
  const nLat = fields.lats.length;
  const nLon = fields.lons.length;
  const grid: number[][] = [];
  for (let i = 0; i < nLat; i++) {
    const row = new Array<number>(nLon);
    for (let j = 0; j < nLon; j++) {
      // collect this cell's series, ignore zero/dry days for a meaningful p90
      const series: number[] = [];
      for (let t = 0; t < nT; t++) {
        const v = fields.rainfall[t][i][j];
        if (v > 0) series.push(v);
      }
      if (series.length === 0) {
        row[j] = Infinity; // never "heavy"
        continue;
      }
      series.sort((a, b) => a - b);
      const idx = Math.min(
        series.length - 1,
        Math.max(0, Math.floor((percentile / 100) * (series.length - 1)))
      );
      row[j] = series[idx];
    }
    grid.push(row);
  }
  P90_CACHE.set(fields, { pct: percentile, grid });
  return grid;
}

/**
 * Apply the rainfall scenario transform to a single baseline value at a cell.
 * `tForOnset` is used by callers to pull the onset-shifted source day.
 */
function transformRainValue(
  baseValue: number,
  sc: ScenarioState,
  phys: WhatIfPhysics,
  heavyThreshold: number
): number {
  let v = baseValue * (1 + sc.rain_pct / 100);
  // Clausius–Clapeyron intensification of heavy-rain days under warming.
  if (sc.temp_offset !== 0 && baseValue >= heavyThreshold) {
    const cc = 1 + (phys.ccPctPerDegC / 100) * sc.temp_offset;
    // apply CC to the (already %-scaled) value, on top of the linear change
    v = v * cc;
  }
  return Math.max(0, v);
}

/**
 * Compute the scenario field for ONE timestep (for the map), returning a fresh
 * [lat][lon] grid. Handles onset roll on the time axis.
 */
export function scenarioFieldAtTime(
  fields: FieldsDaily,
  variable: BaseVariableKey,
  timeIndex: number,
  sc: ScenarioState,
  phys: WhatIfPhysics
): number[][] {
  const nT = fields[variable].length;
  const nLat = fields.lats.length;
  const nLon = fields.lons.length;

  if (variable === "tmax" || variable === "tmin") {
    const src = fields[variable][timeIndex];
    if (sc.temp_offset === 0) return src;
    const out: number[][] = [];
    for (let i = 0; i < nLat; i++) {
      const row = new Array<number>(nLon);
      for (let j = 0; j < nLon; j++) row[j] = src[i][j] + sc.temp_offset;
      out.push(row);
    }
    return out;
  }

  // rainfall: onset roll selects the SOURCE day; positive shift = later monsoon
  // (so day t shows what day (t - shift) used to be).
  const srcDay = mod(timeIndex - sc.onset_shift, nT);
  const src = fields.rainfall[srcDay];
  if (isBaseline(sc)) return src;

  const thr = heavyRainThresholdGrid(fields, phys.heavyRainPercentile);
  const out: number[][] = [];
  for (let i = 0; i < nLat; i++) {
    const row = new Array<number>(nLon);
    for (let j = 0; j < nLon; j++) {
      row[j] = transformRainValue(src[i][j], sc, phys, thr[i][j]);
    }
    out.push(row);
  }
  return out;
}

/**
 * Compute a single cell's full-year series under the scenario (for charts).
 * Returns baseline and scenario arrays so the chart can overlay both.
 */
export function scenarioSeriesAtCell(
  fields: FieldsDaily,
  variable: BaseVariableKey,
  i: number,
  j: number,
  sc: ScenarioState,
  phys: WhatIfPhysics
): { baseline: number[]; scenario: number[] } {
  const nT = fields[variable].length;
  const baseline = new Array<number>(nT);
  const scenario = new Array<number>(nT);

  if (variable === "tmax" || variable === "tmin") {
    for (let t = 0; t < nT; t++) {
      const b = fields[variable][t][i][j];
      baseline[t] = b;
      scenario[t] = b + sc.temp_offset;
    }
    return { baseline, scenario };
  }

  const thr = heavyRainThresholdGrid(fields, phys.heavyRainPercentile)[i][j];
  for (let t = 0; t < nT; t++) {
    baseline[t] = fields.rainfall[t][i][j];
    const srcDay = mod(t - sc.onset_shift, nT);
    scenario[t] = transformRainValue(
      fields.rainfall[srcDay][i][j],
      sc,
      phys,
      thr
    );
  }
  return { baseline, scenario };
}

export interface ImpactSummary {
  variable: BaseVariableKey;
  // Rainfall-specific
  baselineSeasonalRain?: number; // region-mean seasonal total (mm)
  scenarioSeasonalRain?: number;
  deltaSeasonalRain?: number;
  deltaSeasonalRainPct?: number;
  baselineExtremeDays?: number; // region-mean count of >p90 days
  scenarioExtremeDays?: number;
  deltaExtremeDays?: number;
  // Temperature-specific
  baselineMeanTemp?: number;
  scenarioMeanTemp?: number;
  deltaMeanTemp?: number;
}

/**
 * Region-mean impact summary comparing baseline vs scenario across the full
 * year & grid. Computed for the currently-selected base variable.
 */
export function computeImpactSummary(
  fields: FieldsDaily,
  variable: BaseVariableKey,
  sc: ScenarioState,
  phys: WhatIfPhysics
): ImpactSummary {
  const nT = fields[variable].length;
  const nLat = fields.lats.length;
  const nLon = fields.lons.length;
  const ncell = nLat * nLon;

  if (variable === "tmax" || variable === "tmin") {
    let sum = 0;
    for (let t = 0; t < nT; t++)
      for (let i = 0; i < nLat; i++)
        for (let j = 0; j < nLon; j++) sum += fields[variable][t][i][j];
    const baselineMeanTemp = sum / (nT * ncell);
    return {
      variable,
      baselineMeanTemp,
      scenarioMeanTemp: baselineMeanTemp + sc.temp_offset,
      deltaMeanTemp: sc.temp_offset,
    };
  }

  // Rainfall: seasonal total (region-mean) + extreme (>p90) day counts.
  const thr = heavyRainThresholdGrid(fields, phys.heavyRainPercentile);
  let baseTotal = 0;
  let scenTotal = 0;
  let baseExtreme = 0;
  let scenExtreme = 0;
  for (let i = 0; i < nLat; i++) {
    for (let j = 0; j < nLon; j++) {
      const cellThr = thr[i][j];
      for (let t = 0; t < nT; t++) {
        const b = fields.rainfall[t][i][j];
        baseTotal += b;
        if (b >= cellThr && isFinite(cellThr)) baseExtreme += 1;

        const srcDay = mod(t - sc.onset_shift, nT);
        const s = transformRainValue(
          fields.rainfall[srcDay][i][j],
          sc,
          phys,
          cellThr
        );
        scenTotal += s;
        if (s >= cellThr && isFinite(cellThr)) scenExtreme += 1;
      }
    }
  }
  const baselineSeasonalRain = baseTotal / ncell;
  const scenarioSeasonalRain = scenTotal / ncell;
  const deltaSeasonalRain = scenarioSeasonalRain - baselineSeasonalRain;
  return {
    variable,
    baselineSeasonalRain,
    scenarioSeasonalRain,
    deltaSeasonalRain,
    deltaSeasonalRainPct:
      baselineSeasonalRain > 0
        ? (deltaSeasonalRain / baselineSeasonalRain) * 100
        : 0,
    baselineExtremeDays: baseExtreme / ncell,
    scenarioExtremeDays: scenExtreme / ncell,
    deltaExtremeDays: (scenExtreme - baseExtreme) / ncell,
  };
}
