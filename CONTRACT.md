# Data Contract — Bharat Climate Twin serving artifacts

**Version `1.0`** · Produced by `pipeline/run_pipeline.py` · Consumed by the
Next.js + MapLibre + deck.gl frontend and the edge API.

This is the single source of truth for the JSON serving artifacts that power the
**offline demo**. The pipeline writes identical copies to:

- `data/processed/sample/` — canonical, committed to the repo.
- `frontend/public/data/` — the copy the web app fetches statically.

All artifacts are small (total ≈ 1.5 MB), committed, and render with **zero
network**. Numeric fields are rounded (1 dp for physical fields, 3 dp for
uncertainty/weights). Field arrays are indexed `[time][lat][lon]`, with `lat`
ascending **south→north** and `lon` ascending **west→east** (IMD `.grd`
ordering). Pilot region = **Marathwada** `bbox [74.0, 17.5, 79.0, 21.0]`,
`0.25°` grid → **14 lat × 20 lon = 280 cells**.

---

## `metadata.json`
Region, grid, time axis and per-variable display metadata.

```jsonc
{
  "region": "Marathwada drought belt (central Maharashtra)",
  "bbox": [74.0, 17.5, 79.0, 21.0],          // W, S, E, N
  "crs": "EPSG:4326",
  "grid": {
    "res_deg": 0.25,
    "nlat": 14, "nlon": 20,
    "lats": [17.625, ...],                     // length nlat, S→N cell centres
    "lons": [74.125, ...]                      // length nlon, W→E cell centres
  },
  "time": {
    "freq": "daily",
    "start": "2023-01-01", "end": "2023-12-31",
    "n": 365,
    "dates": ["2023-01-01", ...]               // length n, ISO dates
  },
  "variables": {
    "rainfall": {"long_name": "Daily rainfall", "units": "mm/day", "cmap": "rain", "vmin": 0,  "vmax": 80},
    "tmax":     {"long_name": "...",            "units": "°C",      "cmap": "temp", "vmin": 15, "vmax": 48},
    "tmin":     {"long_name": "...",            "units": "°C",      "cmap": "temp", "vmin": 5,  "vmax": 32}
  },
  "h3": {"res_map": 4, "res_region": 2},
  "generated": "2026-06-21T00:00:00Z",
  "data_mode": "synthetic",                     // or "auto-probe+synthetic"
  "version": "1.0"
}
```

## `fields_daily.json`
One representative year of daily fields (the animated map + time-series source).

```jsonc
{
  "dates":    ["2023-01-01", ...],              // length 365
  "lats":     [...],                             // length nlat (14)
  "lons":     [...],                             // length nlon (20)
  "rainfall": [[[...]]],                         // [365][14][20] mm/day, 1 dp
  "tmax":     [[[...]]],                         // [365][14][20] °C, 1 dp
  "tmin":     [[[...]]]                          // [365][14][20] °C, 1 dp
}
```
Size budget: **< ~4 MB** (one year of daily at 14×20 ≈ 1.5 MB).

## `climatology.json`
Monthly region means + annual-by-year series (seasonal & interannual charts).

```jsonc
{
  "months": [1,2,...,12],
  "region_mean": {
    "rainfall": [12 floats],   // monthly TOTAL of daily region-means (mm/month)
    "tmax":     [12 floats],   // monthly MEAN (°C)
    "tmin":     [12 floats]    // monthly MEAN (°C)
  },
  "annual_by_year": {
    "years":    [2010, ..., 2023],
    "rainfall": [...],          // annual TOTAL (mm/yr)
    "tmax":     [...],          // annual MEAN (°C)
    "tmin":     [...]           // annual MEAN (°C)
  }
}
```

## `uncertainty.json`
Per-cell uncertainty from triple collocation, **normalised 0..1** (paired layer).

```jsonc
{
  "lats": [...], "lons": [...],
  "rainfall": [[...]],   // [14][20] in 0..1
  "tmax":     [[...]],   // [14][20] in 0..1
  "tmin":     [[...]]    // [14][20] in 0..1
}
```

## `scenarios.json`
What-if controls, physics, and presets (drives the slider panel + GPU deltas).

```jsonc
{
  "controls": {
    "temp_offset": {"label": "...", "unit": "°C",   "min": -2,  "max": 5,  "step": 0.5, "default": 0},
    "rain_pct":    {"label": "...", "unit": "%",    "min": -50, "max": 50, "step": 5,   "default": 0},
    "onset_shift": {"label": "...", "unit": "days", "min": -30, "max": 30, "step": 5,   "default": 0}
  },
  "physics": {
    "clausius_clapeyron_pct_per_degC": 7.0,
    "notes": "ΔT adds to tmax/tmin; rain_pct scales totals; CC amplifies heavy-rain (>p90) intensity by 7%/°C; onset_shift rolls the monsoon seasonal cycle"
  },
  "presets": [
    {"id": "baseline",       "label": "Baseline",       "temp_offset": 0,   "rain_pct": 0,   "onset_shift": 0},
    {"id": "warming_2c",     "label": "+2 °C warming",  "temp_offset": 2,   "rain_pct": 0,   "onset_shift": 0},
    {"id": "weak_monsoon",   "label": "Weak monsoon",   "temp_offset": 1,   "rain_pct": -20, "onset_shift": 10},
    {"id": "strong_monsoon", "label": "Strong monsoon", "temp_offset": 0.5, "rain_pct": 25,  "onset_shift": -5}
  ]
}
```

## `sources.json`
The ≥30-source catalog powering the "Data Sources" panel (multi-satellite story).

```jsonc
{
  "count": 44,
  "sources": [
    {"name": "IMD Gridded Rainfall 0.25°", "type": "gauge", "role": "ANCHOR TRUTH (rainfall)",
     "res": "0.25°, daily, 1901–", "provider": "IMD Pune", "access": "IMDLIB:rain"},
    // ... ≥30 entries; types ∈ {gauge, satellite, reanalysis, merged, model, hydrology, geo}
  ]
}
```

## `metrics.json`
Stub for model-evaluation metrics; **populated later by the models worker**.

```jsonc
{ "models": [], "ensemble": {}, "note": "populated by model training" }
```
