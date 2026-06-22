# Bharat Climate Twin

### AI-Powered Digital Twin of India's Climate
**ISRO Bharatiya Antariksh Hackathon (BAH) 2026 — Problem Statement 5**

A high-fidelity, **uncertainty-aware**, **edge-served** digital twin of India's
climate (rainfall + temperature), built on India's national datasets and an
indigenous, open, free-tier stack. The Proof-of-Concept focuses on **daily
rainfall and max/min temperature** over the **Marathwada drought belt**
(`bbox [74.0, 17.5, 79.0, 21.0]`, `0.25°` grid).

> This repository contains the engineering blueprint
> ([`ARCHITECTURE.md`](ARCHITECTURE.md)) and a **runnable data foundation**: a
> multi-source ingestion pipeline plus a physically-plausible synthetic
> generator that always produces the precomputed serving artifacts for an
> **offline, zero-network demo**.

---

## Why this is a *twin*, not a dashboard

PS5 asks for a "virtual replica" that *fuses heterogeneous data*, *continuously
evolves*, *integrates several models to consider uncertainty*, and supports
*what-if* simulation. We restate each verb as a term of art and build it:

| PS5 verb | What we build |
|---|---|
| "fuses heterogeneous datasets" | **Data assimilation** — two-stage Bayesian fusion of **30+ cross-validating sources** onto the **IMD gridded ground-truth anchor** |
| "continuously evolves" | **Cycled assimilation** (DA-in-the-loop heartbeat) |
| "integrates several models for uncertainty" | A **multi-model ML ensemble** (trees + ConvLSTM + U-Net + classical + FM forcing) fused with stacking + EMOS + **conformal** calibration |
| "what-if simulation" | A **client-side GPU what-if engine** — `+2 °C`, `−20 % monsoon`, onset-shift applied as a sub-second shader delta |
| "virtual replica" + uncertainty | A **per-pixel uncertainty field** shipped alongside every value (a twin without uncertainty is just a map) |

### Three headline pillars

1. **Multi-satellite robustness (never single-source).** 44 datasets cataloged
   (≥30 used): Indian — IMD gridded (×5), INSAT-3D/3DR/3DS LST/SST/IMC,
   Oceansat-3, IMDAA, Bhuvan, NICES, India-WRIS; global — GPM IMERG, GSMaP,
   CHIRPS, ERA5/ERA5-Land, MODIS/VIIRS LST, SMAP, GRACE-FO, Sentinel,
   Himawari/Meteosat-IODC/FengYun. Curated for **independent error structures**
   so satellites fill each other's gaps and **triple collocation** is valid.

2. **O(1) edge serving.** The India grid is tiny (0.25° ≈ 17k cells; the pilot
   is 280 cells), so we **precompute everything offline** and serve constant-time
   from a dual-chunked **Zarr** cube + **COG** + **PMTiles** + **H3**-indexed
   aggregates on Cloudflare R2/KV/Workers. Every interactive query reduces to a
   deterministic address (point → H3 cell → KV lookup), not a search.

3. **30+ methods, cross-verifying.** Two ensembles, one philosophy — on the
   *data* side ≥30 datasets cross-validate; on the *model* side a diverse
   ensemble lets methods cover each other's failure modes, fused and adversarially
   scored against held-out IMD observations with a **leakage-free CV protocol**.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full 16-section build spec
(data layer §4, DA/modeling §6, O(1) serving §7, API §10, repo structure §12)
and [`research/`](research/) for the source EO/method/platform catalogs.

---

## Architecture at a glance

```
L1 Observation  →  L2 Ingestion/Harmonize  →  L3 Modeling + Data Assimilation
       │                     │                          │
   IMD anchor          regrid to 0.25°            OI/Kriging-KED merge
   INSAT/IMERG/        unify units/calendar       + ML ensemble (DA-in-loop)
   ERA5-Land/MODIS     quantile-map bias-correct          │
       │                     │                            ▼
       └─────────────────────┴──────────────►  L4 State store (value + σ)
                                                 dual-chunked Zarr · COG ·
                                                 PMTiles · H3 GeoParquet
                                                          │
                              L5 Edge services  ◄─────────┘
                              (Workers/KV, what-if engine, UQ)
                                                          │
                              L6 Next.js + MapLibre + deck.gl dashboard
                              L7 feedback: new obs re-assimilate; user what-if
```

This repo implements **L1–L4** for the data foundation: the ingestion clients,
harmonization, two-stage fusion (quantile mapping + OI merge + triple
collocation), H3 keying, and export of the serving artifacts. L5/L6 (edge API +
frontend) consume the JSON contract below.

---

## Quickstart

### 1. Data pipeline — generate the offline-demo artifacts (no network, no deps)

```bash
# Always works on the Python standard library alone (no numpy/xarray needed):
make sample
#  └─ equivalent to:  python -m pipeline.run_pipeline --mode synthetic
```

This writes 7 small JSON artifacts (≈ 1.5 MB total) to **both**
`data/processed/sample/` and `frontend/public/data/`. They are committed and are
the complete dataset for the offline demo.

For the **real, network-backed** path (probes IMD/IMERG/ERA5-Land/MODIS/INSAT/
CHIRPS, falls back to synthetic where credentials/network are missing):

```bash
make install          # optional: install the real-ingestion clients
make pipeline         # python -m pipeline.run_pipeline --mode auto
```

Verify everything compiles and the artifacts conform to the contract:

```bash
make verify
```

### 2. Backend (added by the API worker)

```bash
make backend          # → cd backend && uvicorn app.main:app --reload   (FastAPI + TiTiler)
```

### 3. Frontend (added by the UI worker)

```bash
make frontend         # → cd frontend && npm install && npm run dev      (Next.js + MapLibre + deck.gl)
```

---

## What the synthetic generator gets right

The offline demo must look believable. `pipeline/synthetic.py` encodes real
monsoon physics (verified in the build):

- **SW-monsoon seasonality** — JJAS rainfall ≈ **270×** the near-dry winter.
- **West→east gradient** — Western Ghats edge ≈ **4.8×** wetter than the
  interior Marathwada rain-shadow; interior cells fall to ~660 mm/yr (drought-realistic).
- **Pre-monsoon heat** — May Tmax peak (~38 °C), monsoon cooling (~26 °C in July).
- **Rain ↔ temperature anti-correlation** in the monsoon (**r ≈ −0.58**).
- **Wet/dry spells** — Markov rainfall occurrence + Gamma intensity.
- **Interannual ENSO-like variability** — 2015 El Niño deficit vs 2022 La Niña surplus.

It runs deterministically and **on the standard library alone**, transparently
using numpy for speed when available.

---

## Repository layout

```
bah2026-ps5/
├─ README.md                  ← you are here
├─ ARCHITECTURE.md            ← the 16-section engineering blueprint
├─ CONTRACT.md                ← the JSON serving-artifact data contract (v1.0)
├─ LICENSE                    ← MIT (code) + third-party data notice
├─ Makefile                   ← sample / pipeline / verify / clean / backend / frontend
├─ idea.md                    ← the PS5 problem statement
├─ research/                  ← EO datasets, O(1) platform, AI/ML, DA, viz, data-access
│
├─ pipeline/                  ← the data foundation (this worker)
│   ├─ requirements.txt
│   ├─ config.py              ← bbox, grid, time, variables, H3, 44-source registry, TC triplets
│   ├─ synthetic.py           ← physically-plausible generator (pure-stdlib fallback)
│   ├─ harmonize.py           ← regrid/align to the common 0.25° grid (xarray)
│   ├─ fusion.py              ← quantile mapping + OI merge + triple collocation
│   ├─ h3_index.py            ← O(1) lat/lon→H3 cell (pure-python fallback)
│   ├─ export.py              ← JSON artifacts (stdlib) + Zarr/COG (optional)
│   ├─ run_pipeline.py        ← CLI orchestrator (--mode synthetic|auto)
│   └─ ingest/                ← one module per real source (import-guarded)
│       ├─ imd.py             ← IMD .grd via imdlib + numpy.fromfile fallback
│       ├─ imerg.py           ← GPM IMERG V07 (GEE NASA/GPM_L3/IMERG_V07)
│       ├─ era5.py            ← ERA5-Land (GEE ECMWF/ERA5_LAND/DAILY_AGGR + cdsapi)
│       ├─ modis_lst.py       ← MODIS LST (GEE MODIS/061/MOD11A1)
│       ├─ mosdac.py          ← INSAT-3D 3RIMG_L2B_LST/SST/IMC (MOSDAC mdapi.py)
│       └─ chirps.py          ← CHIRPS (GEE UCSB-CHG/CHIRPS/DAILY)
│
├─ data/
│   ├─ raw/                   ← heavy downloads (git-ignored)
│   └─ processed/sample/      ← the committed JSON demo artifacts ✔
│
└─ frontend/public/data/      ← second copy of the JSON artifacts the web app serves ✔
```

(The full monorepo layout — `backend/`, `edge/`, `frontend/`, `models/`,
`precompute/`, `infra/` — is specified in `ARCHITECTURE.md` §12 and populated by
sibling workers.)

---

## Data sources & provenance

This project foregrounds India's national datasets (Atmanirbhar / indigenous
framing) and cross-validates them with global mirrors:

- **Mandated anchor:** IMD gridded `_Bin` rainfall (0.25°) + Tmax/Tmin (1.0°),
  read via [`imdlib`](https://github.com/iamsaswata/imdlib) with a
  `numpy.fromfile` fallback (exact grid specs in `research/06`).
- **Indian satellite:** INSAT-3D/3DR/3DS LST/SST/IMC via ISRO **MOSDAC**.
- **Global mirrors (fast, cross-validating):** Google Earth Engine, Copernicus
  CDS, NASA Earthdata, Microsoft Planetary Computer, anonymous AWS Open Data.

Each ingestion module cites its exact access identifier (GEE asset ID / CDS
dataset / Earthdata short_name / MOSDAC `datasetId`). The full 44-source registry
lives in `pipeline/config.py` and is exported to `sources.json` for the UI's
"Data Sources" panel. **Honour each upstream dataset's licence** when
redistributing derived products (see `LICENSE`).

---

## Serving-artifact contract

The pipeline emits 7 JSON files conforming to [`CONTRACT.md`](CONTRACT.md):
`metadata.json`, `fields_daily.json`, `climatology.json`, `uncertainty.json`,
`scenarios.json`, `sources.json`, `metrics.json`. They are versioned (`"1.0"`),
rounded, and small enough to commit and serve statically.

---

## License

MIT (this project's source code) — see [`LICENSE`](LICENSE). Upstream Earth-
observation and reanalysis datasets are governed by their own terms.
