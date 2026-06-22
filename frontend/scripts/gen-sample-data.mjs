#!/usr/bin/env node
/**
 * gen-sample-data.mjs — Self-contained sample-data generator for the
 * Bharat Climate Twin dashboard (ISRO BAH 2026 PS5).
 *
 * Pure Node (no dependencies). Generates schema-conforming JSON artifacts into
 * frontend/public/data/ so the dashboard runs standalone right now. The
 * data-foundation worker may later overwrite these with richer REAL artifacts
 * using the SAME schema — so the app keeps working unchanged.
 *
 * Physics modelled (a believable monsoon year over the Marathwada pilot grid):
 *   - Monsoon seasonality: dry winter/pre-monsoon, JJAS (Jun–Sep) wet season,
 *     a withdrawal tail in Oct. Daily rainfall is intermittent (many dry days)
 *     with a heavy-tail of intense days, peaking around late July / early Aug.
 *   - West→East gradient: orographic Western Ghats edge (west) is wetter; the
 *     interior rain-shadow (east) is drier — matching ARCHITECTURE §3.1.
 *   - Temperature: hot pre-monsoon (Apr–May), cooled & damped during the
 *     monsoon, mild winter; Tmax > Tmin with a realistic diurnal range that
 *     narrows on rainy days. Mild south→north / elevation gradient.
 *   - Uncertainty: larger over wet/orographic west and during the monsoon
 *     (cloud loss for satellites), smaller in the dry interior — matching the
 *     "per-pixel uncertainty" principle (ARCHITECTURE §4.5).
 *   - Clausius–Clapeyron: encoded in scenarios.json physics block so the
 *     client what-if engine amplifies heavy-rain (>p90) days under warming.
 *
 * CONTRACT (see ARCHITECTURE §9/§10 and the task brief):
 *   metadata.json, fields_daily.json, climatology.json, uncertainty.json,
 *   scenarios.json, sources.json, metrics.json
 */

import { writeFileSync, mkdirSync, existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const FORCE = process.argv.includes("--force") || process.argv.includes("-f");

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const OUT_DIR = resolve(__dirname, "..", "public", "data");

// ----------------------------------------------------------------------------
// Region + grid (Marathwada pilot, ARCHITECTURE §3.1)
// bbox (W,S,E,N) = [74.0, 17.5, 79.0, 21.0]; common analysis grid = 0.25°.
// ----------------------------------------------------------------------------
const REGION = "Marathwada";
const BBOX = [74.0, 17.5, 79.0, 21.0]; // W, S, E, N
const RES_DEG = 0.25;

// Build cell-CENTER coordinates inside the bbox (S→N for lats, W→E for lons),
// matching IMD convention (lon fastest, S→N).
function arange(start, stop, step) {
  const out = [];
  // half-cell inset so centers sit inside the bbox
  for (let v = start + step / 2; v < stop - 1e-9; v += step) {
    out.push(Math.round(v * 1e6) / 1e6);
  }
  return out;
}
const lats = arange(BBOX[1], BBOX[3], RES_DEG); // S → N
const lons = arange(BBOX[0], BBOX[2], RES_DEG); // W → E
const NLAT = lats.length;
const NLON = lons.length;

// ----------------------------------------------------------------------------
// Time axis: 365 daily steps of a representative monsoon year.
// ----------------------------------------------------------------------------
const YEAR = 2024;
const START = new Date(Date.UTC(YEAR, 0, 1));
const N_DAYS = 365;
function isoDate(d) {
  return d.toISOString().slice(0, 10);
}
const dates = [];
for (let i = 0; i < N_DAYS; i++) {
  const d = new Date(START.getTime() + i * 86400000);
  dates.push(isoDate(d));
}
const doy = (i) => i + 1; // day-of-year 1..365

// ----------------------------------------------------------------------------
// Deterministic PRNG (mulberry32) so output is reproducible across runs.
// ----------------------------------------------------------------------------
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(20260621);
// Standard normal via Box–Muller.
function randn() {
  let u = 0;
  let v = 0;
  while (u === 0) u = rand();
  while (v === 0) v = rand();
  return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
}

const TWO_PI = Math.PI * 2;
const round2 = (x) => Math.round(x * 100) / 100;
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));

// Smooth bump in [0,1] centered at `c` (day-of-year) with width `w` (days).
function gauss(d, c, w) {
  const z = (d - c) / w;
  return Math.exp(-0.5 * z * z);
}

// ----------------------------------------------------------------------------
// Spatial gradients (normalized 0..1 across the grid).
//   gx: West(0) → East(1)   — used for the rain-shadow gradient.
//   gy: South(0) → North(1) — used for a mild thermal/latitude gradient.
// ----------------------------------------------------------------------------
function gx(j) {
  return NLON > 1 ? j / (NLON - 1) : 0;
}
function gy(i) {
  return NLAT > 1 ? i / (NLAT - 1) : 0;
}

// Per-cell static fields: a wetness multiplier (orographic west high, interior
// low) plus a little fixed spatial texture so the map isn't a flat ramp.
const wetness = []; // [NLAT][NLON], ~0.45 (dry interior) .. ~1.6 (wet west)
const elev = []; // [NLAT][NLON], 0..1 pseudo-elevation (west ghats high)
for (let i = 0; i < NLAT; i++) {
  wetness.push(new Array(NLON));
  elev.push(new Array(NLON));
  for (let j = 0; j < NLON; j++) {
    const west = 1 - gx(j); // 1 at far-west, 0 at far-east
    // Orographic wet edge in the west, drier rain-shadow interior eastward.
    const oro = 0.45 + 1.15 * Math.pow(west, 1.35);
    // gentle fixed ripples (static "terrain") so fields look spatially rich
    const ripple =
      0.06 * Math.sin(gx(j) * 6.3 + 0.7) * Math.cos(gy(i) * 4.1 - 0.3);
    wetness[i][j] = Math.max(0.3, oro + ripple);
    elev[i][j] = clamp(0.85 * Math.pow(west, 1.6) + 0.1 * gy(i), 0, 1);
  }
}

// ----------------------------------------------------------------------------
// Seasonal envelopes (region-mean, day-of-year driven).
// ----------------------------------------------------------------------------
// Monsoon precip envelope: near-zero pre-monsoon, strong JJAS, Oct tail.
// (DOY ~165 = mid-Jun onset, peak ~205 late-Jul, withdrawal ~280 early-Oct.)
function monsoonEnvelope(d) {
  const main = gauss(d, 205, 34); // late-Jul peak
  const onsetTail = 0.55 * gauss(d, 168, 16); // June ramp
  const withdraw = 0.45 * gauss(d, 270, 20); // Sep–Oct tail
  const winterShowers = 0.05 * gauss(d, 25, 14); // tiny winter blip
  return main + onsetTail + withdraw + winterShowers; // ~0..1.4
}

// Temperature seasonal mean (°C) — pre-monsoon hot, monsoon-damped, mild winter.
function tempSeasonalMean(d) {
  // Base annual cycle peaking in May (~DOY 135), trough in Jan.
  const annual = 29.5 + 6.5 * Math.cos(TWO_PI * (d - 135) / 365);
  // Monsoon cooling dip (clouds/rain) across JJAS.
  const monsoonCool = -3.2 * monsoonEnvelope(d);
  return annual + monsoonCool;
}

// Diurnal range (Tmax-Tmin) — wide in dry pre-monsoon, narrow in wet monsoon.
function diurnalRange(d) {
  return 13.5 - 6.0 * monsoonEnvelope(d); // ~7.5 (wet) .. ~13.5 (dry)
}

// ----------------------------------------------------------------------------
// Generate daily fields.
//   rainfall[t][i][j]  mm/day  (intermittent, heavy-tailed, monsoon-driven)
//   tmax[t][i][j]      °C
//   tmin[t][i][j]      °C
// ----------------------------------------------------------------------------
const rainfall = [];
const tmax = [];
const tmin = [];

// Per-day synoptic "weather" wobble shared across the grid (storm systems).
const synoptic = new Array(N_DAYS);
{
  let s = 0;
  for (let t = 0; t < N_DAYS; t++) {
    // AR(1) red-noise process for slow-moving systems.
    s = 0.82 * s + 0.6 * randn();
    synoptic[t] = s;
  }
}

for (let t = 0; t < N_DAYS; t++) {
  const d = doy(t);
  const env = monsoonEnvelope(d); // 0..~1.4
  const tMean = tempSeasonalMean(d);
  const dRange = diurnalRange(d);
  // Probability the day is "wet" anywhere ramps with the monsoon envelope.
  const wetProbBase = clamp(0.04 + 0.72 * env, 0.02, 0.96);
  // Synoptic boost: active spells raise both coverage and intensity.
  const spell = clamp(1 + 0.45 * synoptic[t], 0.35, 2.2);

  const rfDay = [];
  const txDay = [];
  const tnDay = [];
  for (let i = 0; i < NLAT; i++) {
    const rfRow = new Array(NLON);
    const txRow = new Array(NLON);
    const tnRow = new Array(NLON);
    for (let j = 0; j < NLON; j++) {
      const w = wetness[i][j];

      // --- Rainfall (mm/day) ---
      // Wet-day occurrence: orographic west rains more often & earlier.
      const pWet = clamp(wetProbBase * (0.55 + 0.6 * w) * spell, 0, 0.985);
      let rf = 0;
      if (rand() < pWet) {
        // Intensity: exponential-ish base scaled by season, wetness, spell.
        const base = 6.5 * env * (0.5 + w) * spell;
        const draw = -Math.log(1 - rand()); // Exp(1)
        rf = base * draw;
        // Heavy-tail extreme bursts (orographic convective cells).
        if (rand() < 0.05 * env) {
          rf += (35 + 55 * rand()) * (0.6 + 0.7 * (1 - gx(j)));
        }
        // small noise + clamp to physical range
        rf = Math.max(0, rf + 1.5 * randn());
      }
      rfRow[j] = round2(clamp(rf, 0, 480));

      // --- Temperature (°C) ---
      // Latitude/elevation: cooler north & higher west.
      const geoAdj = -1.4 * gy(i) - 2.6 * elev[i][j];
      // On heavy-rain cells, suppress Tmax & lift Tmin (cloud blanketing).
      const rainCool = -Math.min(6, 0.05 * rf);
      const cellMean = tMean + geoAdj + 0.4 * synoptic[t];
      const localRange = Math.max(
        3.5,
        dRange * (1 - 0.012 * Math.min(rf, 50)) + 0.6 * randn()
      );
      const tx = cellMean + localRange / 2 + rainCool + 0.4 * randn();
      const tn = cellMean - localRange / 2 + 0.25 * Math.min(4, 0.05 * rf) + 0.4 * randn();
      txRow[j] = round2(tx);
      tnRow[j] = round2(Math.min(tn, tx - 0.5)); // enforce Tmin < Tmax
    }
    rfDay.push(rfRow);
    txDay.push(txRow);
    tnDay.push(tnRow);
  }
  rainfall.push(rfDay);
  tmax.push(txDay);
  tmin.push(tnDay);
}

// ----------------------------------------------------------------------------
// Derived: vmin/vmax for colormaps (robust-ish from the generated data).
// ----------------------------------------------------------------------------
function percentile(flatSorted, p) {
  if (flatSorted.length === 0) return 0;
  const idx = clamp(Math.floor((p / 100) * (flatSorted.length - 1)), 0, flatSorted.length - 1);
  return flatSorted[idx];
}
function flatten3(arr3) {
  const out = [];
  for (const day of arr3) for (const row of day) for (const v of row) out.push(v);
  return out;
}
const rfFlatSorted = flatten3(rainfall).sort((a, b) => a - b);
const txFlatSorted = flatten3(tmax).sort((a, b) => a - b);
const tnFlatSorted = flatten3(tmin).sort((a, b) => a - b);

const RAIN_VMAX = Math.max(20, Math.ceil(percentile(rfFlatSorted, 99) / 5) * 5);
const TX_VMIN = Math.floor(percentile(txFlatSorted, 1));
const TX_VMAX = Math.ceil(percentile(txFlatSorted, 99));
const TN_VMIN = Math.floor(percentile(tnFlatSorted, 1));
const TN_VMAX = Math.ceil(percentile(tnFlatSorted, 99));

// ----------------------------------------------------------------------------
// Climatology: monthly region-mean + annual-by-year (synthetic multi-year).
// ----------------------------------------------------------------------------
function monthOf(t) {
  return new Date(START.getTime() + t * 86400000).getUTCMonth(); // 0..11
}
const months = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
const monRainSum = new Array(12).fill(0); // monthly TOTAL (mm) region-mean
const monTxSum = new Array(12).fill(0);
const monTnSum = new Array(12).fill(0);
const monDayCount = new Array(12).fill(0);

for (let t = 0; t < N_DAYS; t++) {
  const m = monthOf(t);
  let rfMean = 0;
  let txMean = 0;
  let tnMean = 0;
  for (let i = 0; i < NLAT; i++) {
    for (let j = 0; j < NLON; j++) {
      rfMean += rainfall[t][i][j];
      txMean += tmax[t][i][j];
      tnMean += tmin[t][i][j];
    }
  }
  const ncell = NLAT * NLON;
  monRainSum[m] += rfMean / ncell; // accumulate daily region-mean → monthly total
  monTxSum[m] += txMean / ncell;
  monTnSum[m] += tnMean / ncell;
  monDayCount[m] += 1;
}
const clim = {
  rainfall: monRainSum.map((v) => round2(v)), // monthly total rainfall (mm)
  tmax: monTxSum.map((v, m) => round2(v / monDayCount[m])),
  tmin: monTnSum.map((v, m) => round2(v / monDayCount[m])),
};

// Synthetic inter-annual record (10 years) with monsoon variability so the
// climatology panel has a believable annual time-series. Anchored on the
// generated year's seasonal totals.
const baseAnnualRain = clim.rainfall.reduce((a, b) => a + b, 0);
const baseAnnualTx = clim.tmax.reduce((a, b) => a + b, 0) / 12;
const baseAnnualTn = clim.tmin.reduce((a, b) => a + b, 0) / 12;
const years = [];
const annRain = [];
const annTx = [];
const annTn = [];
for (let y = 2015; y <= 2024; y++) {
  years.push(y);
  const k = y - 2015;
  // ENSO-like low-frequency wobble + warming trend.
  const enso = Math.sin(TWO_PI * (k / 4.3) + 0.6);
  annRain.push(round2(baseAnnualRain * (1 + 0.16 * enso + 0.05 * randn())));
  annTx.push(round2(baseAnnualTx + 0.04 * k + 0.5 * enso * -0.3 + 0.15 * randn()));
  annTn.push(round2(baseAnnualTn + 0.05 * k + 0.2 * randn()));
}

const climatology = {
  months,
  region_mean: {
    rainfall: clim.rainfall,
    tmax: clim.tmax,
    tmin: clim.tmin,
  },
  annual_by_year: {
    years,
    rainfall: annRain,
    tmax: annTx,
    tmin: annTn,
  },
  units: { rainfall: "mm/month", tmax: "degC", tmin: "degC" },
  note: "Sample climatology. Monthly region-mean rainfall is a monthly TOTAL (mm); temperatures are monthly means.",
};

// ----------------------------------------------------------------------------
// Uncertainty (1-sigma) per cell, per variable — static field.
//   Larger over wet/orographic west & where seasonal rainfall is high
//   (satellite cloud loss in the monsoon); smaller in the dry interior.
// ----------------------------------------------------------------------------
// seasonal-total rainfall per cell (drives rain uncertainty magnitude)
const cellSeasonRain = [];
for (let i = 0; i < NLAT; i++) {
  cellSeasonRain.push(new Array(NLON).fill(0));
}
for (let t = 0; t < N_DAYS; t++) {
  for (let i = 0; i < NLAT; i++) {
    for (let j = 0; j < NLON; j++) {
      cellSeasonRain[i][j] += rainfall[t][i][j];
    }
  }
}
let maxSeason = 0;
for (let i = 0; i < NLAT; i++)
  for (let j = 0; j < NLON; j++) maxSeason = Math.max(maxSeason, cellSeasonRain[i][j]);

const uncRain = [];
const uncTx = [];
const uncTn = [];
for (let i = 0; i < NLAT; i++) {
  const ur = new Array(NLON);
  const utx = new Array(NLON);
  const utn = new Array(NLON);
  for (let j = 0; j < NLON; j++) {
    const wet = maxSeason > 0 ? cellSeasonRain[i][j] / maxSeason : 0; // 0..1
    // Rain uncertainty grows with wetness + orographic complexity.
    ur[j] = round2(1.2 + 9.0 * wet + 1.5 * elev[i][j] + 0.4 * Math.abs(randn()));
    // Temperature uncertainty: a bit higher where cloudy/wet (less clear-sky LST).
    utx[j] = round2(0.6 + 1.4 * wet + 0.6 * elev[i][j] + 0.15 * Math.abs(randn()));
    utn[j] = round2(0.5 + 1.1 * wet + 0.5 * elev[i][j] + 0.12 * Math.abs(randn()));
  }
  uncRain.push(ur);
  uncTx.push(utx);
  uncTn.push(utn);
}
let uncRainMax = 0;
for (let i = 0; i < NLAT; i++)
  for (let j = 0; j < NLON; j++) uncRainMax = Math.max(uncRainMax, uncRain[i][j]);

const uncertainty = {
  lats,
  lons,
  rainfall: uncRain,
  tmax: uncTx,
  tmin: uncTn,
  units: { rainfall: "mm/day (1-sigma)", tmax: "degC (1-sigma)", tmin: "degC (1-sigma)" },
  note: "Sample per-pixel 1-sigma uncertainty (fusion + ensemble proxy). Higher over wet/orographic west.",
};

// ----------------------------------------------------------------------------
// metadata.json — drives the whole client (grid, time, variables, colormaps).
// ----------------------------------------------------------------------------
const metadata = {
  generated: new Date().toISOString(),
  generator: "frontend/scripts/gen-sample-data.mjs (synthetic sample data)",
  region: REGION,
  region_label: "Marathwada / central Maharashtra drought belt",
  bbox: BBOX,
  crs: "EPSG:4326",
  grid: {
    res_deg: RES_DEG,
    nlat: NLAT,
    nlon: NLON,
    lats,
    lons,
  },
  time: {
    freq: "daily",
    start: dates[0],
    end: dates[dates.length - 1],
    n: N_DAYS,
    dates,
  },
  variables: {
    rainfall: {
      label: "Rainfall",
      units: "mm/day",
      cmap: "rain",
      vmin: 0,
      vmax: RAIN_VMAX,
    },
    tmax: {
      label: "Max Temperature",
      units: "degC",
      cmap: "temp",
      vmin: TX_VMIN,
      vmax: TX_VMAX,
    },
    tmin: {
      label: "Min Temperature",
      units: "degC",
      cmap: "temp",
      vmin: TN_VMIN,
      vmax: TN_VMAX,
    },
    uncertainty: {
      label: "Uncertainty",
      units: "1-sigma",
      cmap: "uncertainty",
      vmin: 0,
      vmax: Math.ceil(uncRainMax),
      note: "Uncertainty magnitude shown for the currently-selected base variable.",
    },
  },
  h3: { res_rain: 4, res_temp: 3, res_national: 2 },
  notes:
    "SAMPLE data generated client-side for standalone runs. Real artifacts " +
    "(same schema) may overwrite these. Rainfall is intermittent & heavy-tailed; " +
    "west→east rain-shadow gradient; monsoon (JJAS) seasonality.",
};

// ----------------------------------------------------------------------------
// fields_daily.json — the animated cube the map renders.
// ----------------------------------------------------------------------------
const fields_daily = {
  dates,
  lats,
  lons,
  rainfall,
  tmax,
  tmin,
};

// ----------------------------------------------------------------------------
// scenarios.json — what-if controls, physics, presets (ARCHITECTURE §8).
// ----------------------------------------------------------------------------
const scenarios = {
  controls: {
    temp_offset: { label: "Temperature change", unit: "°C", min: -2, max: 5, step: 0.5, default: 0 },
    rain_pct: { label: "Rainfall change", unit: "%", min: -50, max: 50, step: 5, default: 0 },
    onset_shift: { label: "Monsoon onset shift", unit: "days", min: -20, max: 20, step: 1, default: 0 },
  },
  physics: {
    clausius_clapeyron_pct_per_degC: 7,
    heavy_rain_percentile: 90,
    notes:
      "Heavy-rain (>p90) days are additionally intensified by " +
      "clausius_clapeyron_pct_per_degC/100 * ΔT (Clausius–Clapeyron). " +
      "tmax'=tmax+ΔT, tmin'=tmin+ΔT, rainfall'=rainfall*(1+ΔP/100); " +
      "onset_shift rolls the rainfall time axis by N days.",
  },
  presets: [
    { id: "baseline", label: "Baseline", temp_offset: 0, rain_pct: 0, onset_shift: 0 },
    { id: "warming_2c", label: "+2°C warming", temp_offset: 2, rain_pct: 0, onset_shift: 0 },
    { id: "weak_monsoon", label: "Weak monsoon / drought", temp_offset: 1, rain_pct: -25, onset_shift: 10 },
    { id: "strong_monsoon", label: "Strong monsoon / flood", temp_offset: 0.5, rain_pct: 20, onset_shift: -7 },
    { id: "compound", label: "Compound: +2°C & −10% rain", temp_offset: 2, rain_pct: -10, onset_shift: 5 },
  ],
};

// ----------------------------------------------------------------------------
// sources.json — the 30+ datasets (multi-satellite robustness showcase).
// Mirrors ARCHITECTURE §4.1.
// ----------------------------------------------------------------------------
const sources = {
  note: "Consolidated multi-source dataset catalogue (ARCHITECTURE §4.1). >=30 sources; 15+ Indian-origin.",
  sources: [
    { name: "IMD Gridded Rainfall 0.25°", type: "Gauge grid", role: "ANCHOR TRUTH (rain)", res: "0.25°, daily, 1901–", provider: "IMD", access: "imdlib" },
    { name: "IMD Gridded Tmax 1.0°", type: "Gauge grid", role: "ANCHOR TRUTH (Tmax)", res: "1.0°, daily, 1951–", provider: "IMD", access: "imdlib" },
    { name: "IMD Gridded Tmin 1.0°", type: "Gauge grid", role: "ANCHOR TRUTH (Tmin)", res: "1.0°, daily, 1951–", provider: "IMD", access: "imdlib" },
    { name: "IMD AWS/ARG network", type: "Station", role: "Point validation / downscaling", res: "sub-daily, NRT", provider: "IMD", access: "mausam.imd.gov.in" },
    { name: "IMD merged satellite-gauge rain", type: "Merged grid", role: "Benchmark product", res: "0.25°, daily", provider: "IMD", access: "imdpune.gov.in" },
    { name: "INSAT-3D/3DR/3DS LST (3RIMG_L2B_LST)", type: "Geo satellite", role: "High-cadence skin-T", res: "4 km, 30-min", provider: "ISRO/MOSDAC", access: "mdapi.py" },
    { name: "INSAT SST (3RIMG_L2B_SST)", type: "Geo satellite", role: "Diurnal SST", res: "4 km, 30-min", provider: "ISRO/MOSDAC", access: "mdapi.py" },
    { name: "INSAT Rainfall (IMC/Hydro-Est.)", type: "Geo satellite", role: "Geostationary QPE", res: "~4 km, 30-min", provider: "ISRO/MOSDAC", access: "mdapi.py" },
    { name: "INSAT Imager L1C", type: "Geo satellite", role: "Cloud/WV/Tb backbone", res: "1 km VIS / 4 km IR", provider: "ISRO/MOSDAC", access: "mdapi.py" },
    { name: "GPM IMERG V07", type: "Satellite (MW+IR)", role: "Primary satellite rain", res: "0.1°, 30-min", provider: "NASA/JAXA", access: "GEE / earthaccess / S3" },
    { name: "GSMaP v7/v6", type: "Satellite (MW+IR)", role: "Independent MW+IR rain", res: "0.1°, hourly", provider: "JAXA", access: "GEE" },
    { name: "CHIRPS v2/v3", type: "Station-blended", role: "Station-blended rain", res: "0.05°, daily", provider: "UCSB-CHG", access: "GEE" },
    { name: "CMORPH", type: "Satellite (MW+IR)", role: "MW-propagated IR rain", res: "8 km / 0.25°", provider: "NOAA", access: "GEE" },
    { name: "PERSIANN-CDR / PDIR-Now", type: "Satellite (ANN IR)", role: "ANN IR rain, NRT", res: "0.04–0.25°", provider: "CHRS/NOAA", access: "GEE / CHRS portal" },
    { name: "MSWEP v3", type: "Merged", role: "SOTA merged benchmark", res: "0.1°, 3-hourly", provider: "GloH2O", access: "gloh2o.org" },
    { name: "ERA5", type: "Reanalysis", role: "Gap-free backbone", res: "0.25°, hourly", provider: "ECMWF", access: "CDS / GEE / S3" },
    { name: "ERA5-Land", type: "Reanalysis", role: "Best gap-free 2 m T", res: "9 km, hourly", provider: "ECMWF", access: "CDS / GEE" },
    { name: "IMDAA (NCMRWF)", type: "Reanalysis", role: "India-specific reanalysis", res: "12 km, hourly", provider: "NCMRWF", access: "rds.ncmrwf.gov.in" },
    { name: "MERRA-2", type: "Reanalysis", role: "Aerosol-aware, independent", res: "0.5°, hourly", provider: "NASA", access: "earthaccess / GEE" },
    { name: "NCEP/NCAR R1", type: "Reanalysis", role: "Long independent baseline", res: "~1.9°, 6-hourly", provider: "NOAA", access: "NOAA PSL OPeNDAP" },
    { name: "JRA-3Q (JMA)", type: "Reanalysis", role: "Asian-centric reanalysis", res: "~0.375°, 3-hourly", provider: "JMA", access: "JMA/DIAS" },
    { name: "MODIS MOD11A1/MYD11A1 LST", type: "Polar satellite", role: "Fine LST truth (4×/day)", res: "1 km, daily", provider: "NASA", access: "GEE / earthaccess" },
    { name: "VIIRS VNP21A1D/N LST", type: "Polar satellite", role: "MODIS-continuity LST", res: "1 km, daily", provider: "NASA", access: "GEE" },
    { name: "Landsat 8/9 ST (TIRS)", type: "Polar satellite", role: "Fine-scale LST downscale", res: "100 m, ~8-day", provider: "NASA/USGS", access: "GEE / MPC" },
    { name: "ECOSTRESS", type: "ISS satellite", role: "Ultra-high-res diurnal LST", res: "~70 m, irregular", provider: "NASA", access: "earthaccess / MPC" },
    { name: "Sentinel-3 SLSTR LST", type: "Polar satellite", role: "European independent LST", res: "1 km, 1–2 day", provider: "ESA", access: "MPC" },
    { name: "NOAA OISST v2.1", type: "Merged SST", role: "Gap-free SST baseline", res: "0.25°, daily", provider: "NOAA", access: "GEE" },
    { name: "SMAP L3/L4", type: "Satellite (passive MW)", role: "Soil moisture (T-P feedback)", res: "9 km; L4 3-hourly", provider: "NASA", access: "GEE / earthaccess" },
    { name: "ASCAT (H SAF)", type: "Satellite (active MW)", role: "Active soil moisture", res: "12.5 km, daily", provider: "EUMETSAT", access: "EUMETSAT H SAF" },
    { name: "ESA CCI Soil Moisture v09", type: "Merged ECV", role: "Merged 40-yr SM ECV", res: "0.25°, daily", provider: "ESA", access: "CEDA / CDS" },
    { name: "Sentinel-1 GRD", type: "SAR satellite", role: "All-weather flood/SM", res: "10 m, 6–12 day", provider: "ESA", access: "GEE / MPC" },
    { name: "GRACE/GRACE-FO mascon", type: "Gravimetry satellite", role: "Water-storage anomaly", res: "~3°, monthly", provider: "NASA", access: "earthaccess / GEE" },
    { name: "Sentinel-2 L2A", type: "Optical satellite", role: "NDVI/land-cover covariate", res: "10–60 m, ~5-day", provider: "ESA", access: "GEE / MPC" },
    { name: "Meteosat MSG/MTG (IODC 45.5°E)", type: "Geo satellite", role: "Independent geo over India", res: "1–3 km, 15-min", provider: "EUMETSAT", access: "EUMETSAT Data Store" },
    { name: "Himawari-8/9 AHI", type: "Geo satellite", role: "Independent geo (E edge)", res: "0.5–2 km, 10-min", provider: "JMA", access: "S3 noaa-himawari9" },
    { name: "FengYun-4A/4B AGRI", type: "Geo satellite", role: "Independent Asian geo", res: "0.5–4 km, 15-min", provider: "CMA", access: "CMA NSMC" },
    { name: "Oceansat-3 OSCAT-3 / OCM-3", type: "Polar satellite", role: "Winds / ocean context", res: "25 km / 1 km", provider: "ISRO", access: "MOSDAC / Bhoonidhi" },
    { name: "Bhuvan (NRSC OGC)", type: "OGC services", role: "Admin/LULC overlays", res: "varies", provider: "ISRO/NRSC", access: "WMS/WMTS bhuvan.nrsc.gov.in" },
    { name: "NICES (NRSC) ECVs", type: "ECV products", role: "Indian climate ECVs", res: "1–5 km", provider: "ISRO/NRSC", access: "Bhuvan / MOSDAC" },
    { name: "India-WRIS", type: "Hydrology", role: "Hydrology ground truth", res: "basin/station", provider: "MoWR", access: "indiawris.gov.in" },
  ],
};

// ----------------------------------------------------------------------------
// metrics.json — model performance (placeholder-friendly; populated sample).
// ----------------------------------------------------------------------------
const metrics = {
  note:
    "SAMPLE model-performance metrics (placeholder). Real values produced by " +
    "models/evaluate.py against held-out IMD obs (RMSE/MAE/CSI etc., ARCHITECTURE §15).",
  models: [
    { name: "XGBoost/LightGBM", var: "rainfall", RMSE: 6.8, MAE: 3.1, CSI: 0.52 },
    { name: "ConvLSTM", var: "rainfall", RMSE: 7.4, MAE: 3.5, CSI: 0.49 },
    { name: "U-Net downscaler", var: "tmax", RMSE: 1.12, MAE: 0.83, CSI: null },
    { name: "U-Net downscaler", var: "tmin", RMSE: 0.98, MAE: 0.74, CSI: null },
    { name: "SARIMAX + Analog", var: "rainfall", RMSE: 8.1, MAE: 4.0, CSI: 0.44 },
  ],
  ensemble: {
    method: "Stacking + EMOS + conformal",
    rainfall: { RMSE: 6.1, MAE: 2.8, CSI: 0.57, CRPS: 2.4, coverage_90: 0.9 },
    tmax: { RMSE: 1.02, MAE: 0.76, CRPS: 0.71, coverage_90: 0.91 },
    tmin: { RMSE: 0.9, MAE: 0.68, CRPS: 0.64, coverage_90: 0.92 },
  },
  baselines: {
    persistence: { rainfall_RMSE: 11.2, tmax_RMSE: 2.3 },
    climatology: { rainfall_RMSE: 9.7, tmax_RMSE: 1.9 },
  },
};

// ----------------------------------------------------------------------------
// Write files.
//
// Safety guard: if REAL (non-sample) artifacts are already present, refuse to
// overwrite unless --force is given. The data-foundation pipeline produces the
// same schema and may drop richer artifacts here; we must not clobber them.
// ----------------------------------------------------------------------------
if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });

const metaPath = join(OUT_DIR, "metadata.json");
if (existsSync(metaPath) && !FORCE) {
  let existing = null;
  try {
    existing = JSON.parse(readFileSync(metaPath, "utf8"));
  } catch {
    /* corrupt/empty → safe to regenerate */
  }
  const isSample = (existing?.generator ?? "").includes("sample");
  if (existing && !isSample) {
    console.log(
      "Refusing to overwrite existing REAL data artifacts in public/data/.\n" +
        "These conform to the same schema and the app already runs against them.\n" +
        "Pass --force to regenerate the synthetic sample data anyway:\n" +
        "  npm run gen:data -- --force"
    );
    process.exit(0);
  }
}

function writeJson(name, obj) {
  const p = join(OUT_DIR, name);
  writeFileSync(p, JSON.stringify(obj));
  const kb = (Buffer.byteLength(JSON.stringify(obj)) / 1024).toFixed(1);
  console.log(`  wrote ${name.padEnd(20)} ${kb.padStart(9)} KB`);
}

console.log(`Generating sample data → ${OUT_DIR}`);
console.log(`  grid: ${NLAT} lat × ${NLON} lon = ${NLAT * NLON} cells, ${N_DAYS} days`);
writeJson("metadata.json", metadata);
writeJson("fields_daily.json", fields_daily);
writeJson("climatology.json", climatology);
writeJson("uncertainty.json", uncertainty);
writeJson("scenarios.json", scenarios);
writeJson("sources.json", sources);
writeJson("metrics.json", metrics);
console.log("Done.");
