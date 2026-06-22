# Bharat Climate Twin — O(1) Serving API

A fast **FastAPI** service that preloads the precomputed serving artifacts from
`data/processed/sample/` into memory **once** at startup and answers every query
in **O(1)** via direct index / dict lookups (ARCHITECTURE.md §7, §10, §11).

The pilot grid is tiny — Marathwada at 0.25°, **14 lat × 20 lon × 365 days** —
so the whole cube fits comfortably in RAM. There is **no per-request file I/O and
no scanning** on the hot path: a point becomes a grid index by arithmetic, a date
becomes a time index by dict lookup, a tile is a byte range, and a scenario is a
recompute over in-RAM arrays.

It serves **both**:

1. the **exact JSON artifacts** the dashboard already fetches
   (`frontend/lib/api.ts`), at both the bare filename (`/metadata.json`) and a
   namespaced `/api/...` path — so pointing `NEXT_PUBLIC_API_BASE` at this
   backend "just works"; and
2. the **richer query / scaling endpoints** from ARCHITECTURE.md §10
   (`/api/fields`, `/api/point`, `/api/timeseries`, `/api/whatif`, …).

---

## Quick start

```bash
cd backend
python -m pip install --ignore-installed packaging fastapi "uvicorn[standard]" pydantic
# optional accelerators (the service runs fine without them):
python -m pip install numpy h3

uvicorn app.main:app --reload --port 8000
```

* Interactive OpenAPI docs: <http://localhost:8000/docs>
* Service banner / endpoint index: <http://localhost:8000/>
* Health + diagnostics: <http://localhost:8000/api/health>

By default the service reads artifacts from `../data/processed/sample` (resolved
relative to the repo). Override with the `BCT_DATA_DIR` environment variable:

```bash
BCT_DATA_DIR=/path/to/artifacts uvicorn app.main:app --port 8000
```

### Point the frontend at this backend

The dashboard reads static JSON from `/data/*.json` by default. Set the env var
to switch it to this API (same schema, same filenames):

```bash
# frontend/.env.local
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

`api.ts` then fetches `${NEXT_PUBLIC_API_BASE}/metadata.json`,
`${NEXT_PUBLIC_API_BASE}/fields_daily.json`, etc. — all of which this service
serves verbatim. CORS is enabled for all origins for the demo.

---

## Endpoints

### Artifact endpoints (byte-identical to CONTRACT.md / api.ts)

| Method & path | Also at | Returns |
|---|---|---|
| `GET /api/metadata` | `/metadata.json` | `metadata.json` |
| `GET /api/fields_daily` | `/fields_daily.json` | `fields_daily.json` (full cube) |
| `GET /api/climatology` | `/climatology.json` | `climatology.json` |
| `GET /api/uncertainty` | `/uncertainty.json` | `uncertainty.json` (`?var=` slices) |
| `GET /api/scenarios` | `/scenarios.json` | `scenarios.json` |
| `GET /api/sources` | `/sources.json` | `sources.json` |
| `GET /api/metrics` | `/metrics.json` | `metrics.json` |

### Query / scaling endpoints (ARCHITECTURE §10)

| Method & path | Purpose |
|---|---|
| `GET /api/health` | Liveness + store diagnostics |
| `GET /api/fields?var=&date=` | Single-timestep grid slice (O(1)) |
| `GET /api/point?lat=&lon=` | Nearest cell: full daily series for all vars + uncertainty + climatology |
| `GET /api/timeseries?lat=&lon=&var=&start=&end=` | Cell series + conformal-style bands |
| `GET /api/scenarios/list` | Canonical scenario library as `[{id,label,params}]` |
| `GET /api/forecast` | Forecast frame if `forecast.json` present, else `available:false` |
| `POST /api/whatif` | Server-side scenario recompute (see below) |
| `GET /api/whatif?temp_offset=&rain_pct=&onset_shift=` | GET alias (also accepts `dT`/`dP`/`onset`) |
| `GET /api/tiles/{z}/{x}/{y}.png` | Stub → PMTiles/TiTiler in production (501) |

### Example responses

```jsonc
// GET /api/health
{"status":"ok","service":"bharat-climate-twin-api","version":"1.0","loaded":true,
 "artifacts":["climatology","fields_daily","metadata","metrics","scenarios","sources","uncertainty"],
 "grid":{"res_deg":0.25,"nlat":14,"nlon":20,"ntime":365},"cells":280,
 "h3":{"enabled":true,"res":4,"indexed_cells":126},"numpy":true}
```

```jsonc
// GET /api/point?lat=19&lon=76   (series arrays trimmed)
{"cell_id":"846083dffffffff","i":6,"j":8,"lat":19.125,"lon":76.125,
 "query_lat":19.0,"query_lon":76.0,"dates":["2023-01-01", ...,"2023-12-31"],
 "series":{"rainfall":{"units":"mm/day","values":[0.0,0.0,0.0, ...],"uncertainty":0.397},
           "tmax":{...},"tmin":{...}},
 "climatology":{...}}
```

```jsonc
// POST /api/whatif  body {"temp_offset":2,"rain_pct":-20,"onset_shift":10,"var":"rainfall",
//                          "date":"2023-07-20","lat":19,"lon":76}
{"params":{"temp_offset":2.0,"rain_pct":-20.0,"onset_shift":10.0},
 "var":"rainfall","date":"2023-07-20","match":"recomputed","units":"mm/day",
 "lats":[...],"lons":[...],
 "baseline_field":[[...]],"scenario_field":[[...]],"delta_field":[[...]],
 "impact":{"variable":"rainfall","baselineSeasonalRain":2518.6,"scenarioSeasonalRain":2118.7,
           "deltaSeasonalRain":-399.9,"deltaSeasonalRainPct":-15.88,
           "baselineExtremeDays":16.2,"scenarioExtremeDays":11.7,"deltaExtremeDays":-4.5},
 "series":{"baseline":[...],"scenario":[...]}}
```

---

## What-if physics — matches `frontend/lib/whatif.ts` exactly

The server applies the **same** transforms as the client so an optimistic client
preview and the server answer agree (verified: field diffs `0.0`, impact-summary
diffs `< 1e-10` across multiple scenarios):

```
tmax'     = tmax + temp_offset
tmin'     = tmin + temp_offset
rainfall' = rainfall * (1 + rain_pct/100)
            · heavy-rain days (baseline ≥ per-cell p90 of WET days) are
              additionally amplified by (1 + clausius_clapeyron_pct_per_degC/100 · temp_offset)
onset_shift: roll the rainfall TIME axis by N days (positive = later monsoon;
             day t shows what day (t − shift) used to be, with positive modulo)
```

The impact summary keys (`baselineSeasonalRain`, `deltaSeasonalRainPct`,
`deltaExtremeDays`, `deltaMeanTemp`, …) mirror the client's `ImpactSummary`.

---

## How the O(1) lookups work

* **Point → grid cell.** The analysis grid is a regular 0.25° lattice, so a
  geographic point maps to a cell with closed-form arithmetic — no search:

  ```
  i = round((lat − lat0) / res)        # latitude index  (S → N)
  j = round((lon − lon0) / res)        # longitude index (W → E)
  ```

  where `(lat0, lon0)` is the south-west cell centre. That is O(1).
* **H3 keying.** At startup we also build a dict `{h3_cell_id → (i, j)}` using
  the Uber **H3** library (res-4 for the 0.25° grid, per ARCHITECTURE §3). If
  `h3` is not installed we fall back to a deterministic synthetic cell id
  (`cell-r4-<i>-<j>`) — still an O(1) hash, just not a real H3 index. A click in
  the dashboard can therefore be resolved either by lat/lon arithmetic or by H3
  id, both O(1).
* **Date → time index.** A `{date → index}` dict gives O(1) date resolution; the
  field slice is then a direct array index `fields[var][t]`.
* **Heavy-rain threshold.** The per-cell p90-of-wet-days grid is computed **once**
  at startup (warmed in the lifespan handler), so the first what-if call is also
  O(1) on the hot path.
* **No per-request I/O.** Every artifact is parsed into module-level state in the
  FastAPI **lifespan** loader; requests only read in-memory structures.

`numpy` and `h3` are **optional** (guarded imports). With only `fastapi` +
`uvicorn` + `pydantic` + the Python stdlib, the service still runs and produces
identical numbers (the what-if recompute uses a pure-python path; `numpy`
vectorises it when present).

---

## Layout

```
backend/
├── app/
│   ├── main.py              # FastAPI app + lifespan loader + CORS + /health + /
│   ├── data_store.py        # in-memory O(1) store: index math, H3 dict, p90 grid
│   ├── whatif.py            # what-if physics (mirrors frontend/lib/whatif.ts)
│   ├── models.py            # pydantic response models
│   └── routes/
│       ├── artifacts.py     # verbatim artifact endpoints (api.ts shapes)
│       ├── query.py         # /fields, /point, /timeseries, /forecast, /scenarios/list
│       ├── whatif_routes.py # POST/GET /api/whatif
│       └── tiles.py         # /api/tiles/{z}/{x}/{y}.png stub
├── edge/
│   ├── worker.js            # Cloudflare Worker edge stub (KV/R2 O(1) design, §11)
│   └── wrangler.toml        # Worker config (R2 bucket + KV namespace bindings)
├── requirements.txt
├── Dockerfile               # slim python; bakes artifacts, serves on :8000
└── README.md
```

---

## Docker

```bash
# from the repo root (so the data dir is in the build context):
docker build -t bct-api -f backend/Dockerfile .
docker run --rm -p 8000:8000 bct-api
curl http://localhost:8000/api/health
```

---

## Edge serving (Cloudflare) — `edge/`

`edge/worker.js` + `edge/wrangler.toml` are a documented **stub** of the
production O(1) edge design (ARCHITECTURE §7, §11): the precomputed JSON
artifacts live in **R2** (zero egress, range reads), point/scenario lookups hit
**KV** (`{h3_cell → series}`, `{scenario_hash → delta}`, 0.5–10 ms hot reads),
and map tiles resolve `(z,x,y) → PMTiles Hilbert id → R2 byte range`. The Worker
mirrors the same endpoint paths as this FastAPI service, so the frontend can
point `NEXT_PUBLIC_API_BASE` at either. See `edge/wrangler.toml` for the
`wrangler kv:namespace create` / `wrangler r2 object put` / `wrangler deploy`
steps.
```
