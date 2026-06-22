# Bharat Climate Twin — Frontend Dashboard

Interactive, GPU-accelerated dashboard for the **AI-Powered Digital Twin of
India's Climate** (ISRO Bharatiya Antariksh Hackathon 2026 · Problem Statement 5).

This is the **L6 / Visualization** layer of the architecture in
[`../ARCHITECTURE.md`](../ARCHITECTURE.md) (see §9 Visualization, §8 What-if
engine, §10 API). It renders a full-screen MapLibre basemap with a deck.gl
GPU overlay of the climate field, a play/scrub timeline over 365 daily
timesteps, click-a-point time-series + climatology charts, and a **real-time
client-side what-if scenario engine**.

---

## Quick start

```bash
cd frontend
npm install
npm run gen:data      # generate self-contained sample data into public/data/
npm run dev           # http://localhost:3000
```

> `npm run gen:data` is only needed once (the generated JSON is committed). It
> regenerates the sample dataset if you delete or want to refresh it.

Production build:

```bash
npm run build
npm run start         # serves the production build on :3000
```

Type-check only (no build):

```bash
npm run typecheck     # tsc --noEmit
```

---

## What it does (feature map → task brief)

| Feature | Where |
|---|---|
| Full-screen MapLibre basemap (CARTO dark + **offline graticule fallback**) | `lib/basemap.ts`, `components/MapStage.tsx` |
| deck.gl overlay rendering the grid as a colored field (interleaved `MapboxOverlay`) | `components/MapStage.tsx` (`SolidPolygonLayer` per grid cell) |
| Colormaps (rain: white→blue→purple; temp: blue→yellow→red) + legend | `lib/colormaps.ts`, `components/Legend.tsx` |
| Timeline: play/pause + scrubber over 365 days, `requestAnimationFrame` clock | `components/BottomTimeline.tsx`, clock in `components/Dashboard.tsx` |
| Layer selector (Rainfall / Tmax / Tmin / Uncertainty) | `components/LayerPanel.tsx` |
| Click-a-point → uPlot time-series + ECharts monthly climatology | `components/PointTimeSeries.tsx`, `components/ClimatologyPanel.tsx` |
| **What-if panel** (ΔT, ΔP %, onset shift sliders + presets) | `components/WhatIfPanel.tsx` |
| Real-time scenario recompute + Clausius–Clapeyron + onset roll + impact summary | `lib/whatif.ts` |
| Before/after compare (custom swipe split) | `components/MapStage.tsx` |
| Data Sources drawer (30+ datasets) | `components/SourcesPanel.tsx` |
| Model Performance drawer (metrics.json, placeholder-safe) | `components/MetricsPanel.tsx` |
| Header: title, region selector, About | `components/Header.tsx`, `components/AboutPanel.tsx` |

Keyboard: <kbd>Space</kbd> play/pause · <kbd>←</kbd>/<kbd>→</kbd> step a day.

---

## What-if physics (client-side, instant)

Implemented in `lib/whatif.ts`, matching the contract (ARCHITECTURE §8):

```
tmax'      = tmax + ΔT
tmin'      = tmin + ΔT
rainfall'  = rainfall * (1 + ΔP/100)
             + heavy-rain (>p90) days additionally amplified by
               (clausius_clapeyron_pct_per_degC / 100) * ΔT
onset_shift: roll the rainfall time axis by N days
```

The grid is tiny (≈280 cells × 365 days for the pilot), so the entire cube
lives in the browser and the scenario is recomputed on the client — the map
and charts update with **zero server latency**. Slider drags are debounced
(~180 ms) before committing to the store so dragging stays smooth.

The **impact summary** compares baseline vs scenario across the full year/grid:
Δ seasonal total rainfall (+ %), Δ extreme-rain (>p90) days, and Δ mean temp.

---

## Data contract & data-access layer

The app reads JSON from `/data/*.json` (i.e. files in `public/data/`). A typed
data-access layer (`lib/api.ts`, types in `lib/types.ts`) loads:

| File | Purpose |
|---|---|
| `metadata.json` | region, bbox, crs, grid (lats/lons), time (dates), variables (units/cmap/vmin/vmax) |
| `fields_daily.json` | the daily cube: `rainfall|tmax|tmin` as `[365][nlat][nlon]` |
| `climatology.json` | monthly region-mean + annual-by-year |
| `uncertainty.json` | per-cell 1σ for each variable |
| `scenarios.json` | what-if controls, physics (CC %/°C), presets |
| `sources.json` | the 30+ dataset catalogue |
| `metrics.json` | model performance (placeholder-safe) |

This is the **same schema** the data-foundation worker produces; it can drop
real artifacts into `public/data/` and the app just works. Required files are
`metadata.json` + `fields_daily.json`; the rest degrade gracefully if missing.

### Pointing at a backend

Set `NEXT_PUBLIC_API_BASE` to fetch from the backend instead of static files:

```bash
NEXT_PUBLIC_API_BASE=https://your-edge-api.example.com npm run dev
```

When set, the data layer requests `${NEXT_PUBLIC_API_BASE}/<file>.json`
(e.g. a backend that serves the same artifact filenames). Default is `/data`.

---

## Sample-data generator

`scripts/gen-sample-data.mjs` (pure Node, **no dependencies**) synthesizes a
believable monsoon year over the Marathwada grid using the contract physics:

- Monsoon (JJAS) seasonality with intermittent, heavy-tailed daily rainfall;
- West→East orographic / rain-shadow gradient (wetter Western-Ghats edge);
- Temperature with a hot pre-monsoon, monsoon-damped diurnal range, mild winter;
- Per-pixel uncertainty larger over the wet/cloudy west;
- `scenarios.json` carrying the Clausius–Clapeyron coefficient (7 %/°C).

Output is deterministic (seeded PRNG). Run via `npm run gen:data`.

---

## Architecture / stack

- **Next.js (App Router) + React + TypeScript** — map is `dynamic(..., {ssr:false})`.
- **MapLibre GL JS** (BSD-3, not Mapbox) basemap; **deck.gl** interleaved
  (`@deck.gl/mapbox` `MapboxOverlay({interleaved:true})`) for GPU layers.
- **uPlot** (fast live time-series) + **ECharts** (climatology panels).
- **Zustand** store: `{ variable, timeIndex, playing, scenario, selectedCell, comparing }`
  + loaded artifacts (`lib/store.ts`).
- **TanStack Query** provider is wired (`app/providers.tsx`) for optional
  server-data fetching.

### File tree

```
frontend/
├─ app/
│  ├─ globals.css           # dark "mission-control" theme
│  ├─ layout.tsx            # imports maplibre + uplot CSS
│  ├─ providers.tsx         # TanStack Query
│  └─ page.tsx              # renders <Dashboard/>
├─ components/
│  ├─ Dashboard.tsx         # data load + rAF animation clock + layout
│  ├─ Header.tsx            # title · region selector · drawer toggles
│  ├─ MapStage.tsx          # MapLibre + deck.gl overlay + click + swipe
│  ├─ LeftRail.tsx          # tabs: Layers / What-If
│  ├─ LayerPanel.tsx        # variable + opacity + compare toggle
│  ├─ WhatIfPanel.tsx       # sliders + presets + impact summary
│  ├─ Legend.tsx            # colormap legend
│  ├─ BottomTimeline.tsx    # play/scrub/speed + season track
│  ├─ ChartDock.tsx         # hosts the two charts
│  ├─ PointTimeSeries.tsx   # uPlot
│  ├─ ClimatologyPanel.tsx  # ECharts
│  ├─ Drawer.tsx            # sources / metrics / about
│  ├─ SourcesPanel.tsx
│  ├─ MetricsPanel.tsx
│  └─ AboutPanel.tsx
├─ lib/
│  ├─ types.ts              # data contract types
│  ├─ api.ts                # typed data-access (static or NEXT_PUBLIC_API_BASE)
│  ├─ store.ts              # Zustand store
│  ├─ colormaps.ts          # ramps + legend + value→RGBA
│  ├─ whatif.ts             # scenario engine (CC, onset roll, impact)
│  ├─ grid.ts               # cell geometry + nearest-cell
│  └─ basemap.ts            # CARTO dark + offline graticule styles
├─ scripts/
│  └─ gen-sample-data.mjs   # self-contained sample data generator
└─ public/data/             # generated JSON artifacts (committed so the app runs standalone)
```

---

## Notes / known constraints

- **External basemap tiles**: the app loads CARTO dark raster tiles. If the
  network blocks them, it auto-falls back to a self-contained navy + graticule
  style so the field always renders (ARCHITECTURE P7 demo-reliability).
- **Colormap on the field**: per the ARCHITECTURE the long-term plan is a GPU
  fragment-shader LUT on a `BitmapLayer`. Because the pilot grid is tiny, this
  build colors per-cell `SolidPolygonLayer` fills in JS (instant), which keeps
  the code readable and the picking/hover exact. The colormap module is shaped
  so a `BitmapLayer` + LUT upgrade is a drop-in for national scale-up.
- Responsive: the chart dock hides on narrow screens; the rails shrink.
```
