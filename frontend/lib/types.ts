// Typed data contract for the Bharat Climate Twin dashboard.
// These interfaces mirror the JSON artifacts in frontend/public/data/ (or the
// backend when NEXT_PUBLIC_API_BASE is set). Another worker produces the REAL
// artifacts with this SAME schema, so the app works against either.

export type VariableKey = "rainfall" | "tmax" | "tmin" | "uncertainty";

/** The three variables that have actual daily fields (uncertainty is derived). */
export type BaseVariableKey = "rainfall" | "tmax" | "tmin";

export type ColormapName = "rain" | "temp" | "uncertainty";

export interface VariableMeta {
  label: string;
  units: string;
  cmap: ColormapName;
  vmin: number;
  vmax: number;
  note?: string;
}

export interface GridMeta {
  res_deg: number;
  nlat: number;
  nlon: number;
  /** Cell-center latitudes, S→N, length nlat. */
  lats: number[];
  /** Cell-center longitudes, W→E, length nlon. */
  lons: number[];
}

export interface TimeMeta {
  freq: string;
  start: string;
  end: string;
  n: number;
  /** ISO date strings, length n. */
  dates: string[];
}

export interface Metadata {
  generated?: string;
  generator?: string;
  region: string;
  region_label?: string;
  /** [W, S, E, N] */
  bbox: [number, number, number, number];
  crs: string;
  grid: GridMeta;
  time: TimeMeta;
  // rainfall/tmax/tmin are always present; uncertainty is an optional derived
  // view (some producers omit it from metadata — the app derives its range).
  variables: Record<BaseVariableKey, VariableMeta> &
    Partial<Record<"uncertainty", VariableMeta>>;
  h3?: Record<string, number>;
  notes?: string;
}

/** Daily field cube. Indexed [t][lat][lon]. */
export interface FieldsDaily {
  dates: string[];
  lats: number[];
  lons: number[];
  rainfall: number[][][];
  tmax: number[][][];
  tmin: number[][][];
}

export interface Climatology {
  months: number[];
  region_mean: {
    rainfall: number[]; // 12 — monthly TOTAL (mm)
    tmax: number[]; // 12 — monthly mean (°C)
    tmin: number[]; // 12 — monthly mean (°C)
  };
  annual_by_year: {
    years: number[];
    rainfall: number[];
    tmax: number[];
    tmin: number[];
  };
  units?: Record<string, string>;
  note?: string;
}

/** Static per-cell uncertainty (1-sigma). Indexed [lat][lon]. */
export interface Uncertainty {
  lats: number[];
  lons: number[];
  rainfall: number[][];
  tmax: number[][];
  tmin: number[][];
  units?: Record<string, string>;
  note?: string;
}

export interface ScenarioControl {
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
  default: number;
}

export interface ScenarioPreset {
  id: string;
  label: string;
  temp_offset: number;
  rain_pct: number;
  onset_shift: number;
}

export interface Scenarios {
  controls: {
    temp_offset: ScenarioControl;
    rain_pct: ScenarioControl;
    onset_shift: ScenarioControl;
  };
  physics: {
    clausius_clapeyron_pct_per_degC: number;
    heavy_rain_percentile?: number;
    notes?: string;
  };
  presets: ScenarioPreset[];
}

export interface DataSource {
  name: string;
  type: string;
  role: string;
  res: string;
  provider: string;
  access: string;
}

export interface Sources {
  note?: string;
  sources: DataSource[];
}

export interface ModelMetric {
  name: string;
  var: string;
  RMSE?: number | null;
  MAE?: number | null;
  CSI?: number | null;
  [k: string]: unknown;
}

export interface Metrics {
  note?: string;
  models: ModelMetric[];
  ensemble?: Record<string, unknown>;
  baselines?: Record<string, unknown>;
}

/** Short-range AI forecast frame (data/forecast.json).
 * Indexed [lead][lat][lon]; `leads`/`dates` are length L (e.g. 1..7 days). */
export interface Forecast {
  issue_date: string;
  leads: number[];
  dates: string[];
  lats: number[];
  lons: number[];
  rainfall: number[][][];
  tmax: number[][][];
  tmin: number[][][];
  /** Per-lead, per-cell 1-sigma (absolute units) for each base variable. */
  uncertainty: Record<BaseVariableKey, number[][][]>;
  units?: Record<string, string>;
  model?: string;
  method?: string;
  generated?: string;
}

/** The scenario the user is currently exploring (what-if controls). */
export interface ScenarioState {
  temp_offset: number;
  rain_pct: number;
  onset_shift: number;
}

export const BASELINE_SCENARIO: ScenarioState = {
  temp_offset: 0,
  rain_pct: 0,
  onset_shift: 0,
};

/** Currently-selected grid cell (for the time-series / climatology charts). */
export interface SelectedCell {
  i: number; // lat index
  j: number; // lon index
  lat: number;
  lon: number;
}
