# Deployment Guide — Bharat Climate Twin

**ISRO BAH 2026 · Problem Statement 5 — AI-Powered Digital Twin of India's Climate**

This guide covers running the Bharat Climate Twin locally, then deploying it to a
fast, free-tier-friendly **Cloudflare** edge stack (the chosen production topology
from [`ARCHITECTURE.md`](ARCHITECTURE.md) §11 and `research/06`), plus container
and model-inference options.

The system is intentionally split so each piece deploys independently:

| Component | Path | Role | Production home |
|---|---|---|---|
| **Serving artifacts** | `data/processed/sample/*.json` (+ Zarr/COG/PMTiles at scale) | precomputed, read-only data | **Cloudflare R2** (zero egress) + **KV** (hot metadata) |
| **Edge worker** | `backend/edge/worker.js` + `wrangler.toml` | O(1) tile/point/scenario serving | **Cloudflare Workers** |
| **Backend API** | `backend/` (FastAPI) + `backend/Dockerfile` | heavier/dynamic API + OpenAPI docs | Cloud Run / Fly.io / Render / HF Spaces |
| **Frontend** | `frontend/` (Next.js) | dashboard UI | **Cloudflare Pages** (or Vercel) |
| **Pipeline + models** | `pipeline/`, `models/` | offline precompute + training | GitHub Actions / Modal / HF (offline) |

> **Why this is fast & cheap:** the India grid is tiny (the pilot is 280 cells),
> all artifacts are **precomputed and static**, R2 has **zero egress**, and GPU is
> used only in offline bursts (or avoided entirely via precompute). The whole PoC
> fits comfortably in free tiers.

---

## 1. Local deployment

### 1a. One-command demo (recommended)

```bash
make demo
#  or, directly:
docker compose up --build
```

- Frontend dashboard → **http://localhost:3000**
- Backend API → **http://localhost:8000** (interactive OpenAPI docs at **/docs**,
  health at **/api/health**)

`docker-compose.yml` builds the backend from [`backend/Dockerfile`](backend/Dockerfile)
and the frontend from `frontend/Dockerfile`, wires the frontend's
`NEXT_PUBLIC_API_BASE` to the backend service, and serves the committed sample
artifacts — so the demo runs with **zero external network**.

### 1b. Manual (two terminals)

```bash
# Terminal 1 — backend (FastAPI, loads artifacts into RAM once, O(1) reads)
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000        # --reload for dev

# Terminal 2 — frontend (Next.js + MapLibre + deck.gl)
cd frontend
npm install
NEXT_PUBLIC_API_BASE=http://localhost:8000/api npm run dev   # http://localhost:3000
```

Or start both together with the helper script:

```bash
./scripts/dev.sh
```

**Frontend data source:** if `NEXT_PUBLIC_API_BASE` is **unset**, the dashboard
serves the committed static JSON from `frontend/public/data/` (fully offline). When
set, the data layer fetches `${NEXT_PUBLIC_API_BASE}/<file>.json` from the backend
or edge worker (identical artifact schema — see [`CONTRACT.md`](CONTRACT.md)).

### 1c. Backend container (standalone)

```bash
# Build from the repo root so the data dir is in the build context:
docker build -t bct-api -f backend/Dockerfile .
docker run --rm -p 8000:8000 bct-api
curl http://localhost:8000/api/health        # docs at http://localhost:8000/docs
```

The image **bakes the artifacts in at build time**. To serve a different artifact
set, mount it and override `BCT_DATA_DIR`:

```bash
docker run --rm -p 8000:8000 -v /path/to/data:/data -e BCT_DATA_DIR=/data bct-api
```

### 1d. Regenerate artifacts / retrain before deploying

```bash
python -m pipeline.run_pipeline --mode synthetic   # or: make sample  (rebuild demo JSON)
python -m models.train                             # or: make train  (rebuild metrics.json + forecast.json)
make verify                                         # compile + validate artifacts vs CONTRACT.md
```

The pipeline writes identical copies to **both** `data/processed/sample/` (the
canonical, committed copy) and `frontend/public/data/` (the copy the web app
fetches statically).

---

## 2. Production on Cloudflare (primary stack)

The production topology (ARCHITECTURE §11) puts the **frontend on Cloudflare
Pages**, **precomputed artifacts on R2 + KV**, and the **O(1) hot path on a
Cloudflare Worker** — all behind Cloudflare's 330+-PoP CDN.

```
                 ┌──────────────────── Cloudflare edge (330+ PoPs) ─────────────────────┐
 Browser ──────► │  Pages (Next.js dashboard)  ──API──►  Worker (backend/edge/worker.js) │
 (user GPU)      │                                          │            │               │
                 │                                          ▼            ▼               │
                 │                              R2 (artifacts, COG,   KV (h3_cell→series, │
                 │                              PMTiles, Zarr; 0 egress)  scenario→delta) │
                 └───────────────────────────────────────────────────────────────────────┘
```

### 2a. Artifacts → R2 (zero egress) + KV (hot metadata)

R2 holds the precomputed JSON artifacts (and, at scale, the COG / PMTiles / Zarr /
GeoParquet pyramids). KV holds the O(1) hot lookups — `{h3_cell → series}`,
`{scenario_hash → delta}` and hot metadata. From `backend/edge/`:

```bash
npm i -g wrangler && wrangler login

# 1. Create the R2 bucket and upload the serving artifacts:
wrangler r2 bucket create bct-artifacts
wrangler r2 object put bct-artifacts/metadata.json     --file ../../data/processed/sample/metadata.json
wrangler r2 object put bct-artifacts/fields_daily.json --file ../../data/processed/sample/fields_daily.json
# ...repeat for climatology.json, uncertainty.json, scenarios.json, sources.json, metrics.json

# 2. Create the KV namespace, then paste the returned id into wrangler.toml:
wrangler kv:namespace create ARTIFACTS_KV
```

The bucket name (`bct-artifacts`), R2 binding (`ARTIFACTS`) and KV binding (`KV`)
are already declared in [`backend/edge/wrangler.toml`](backend/edge/wrangler.toml);
replace `REPLACE_WITH_KV_NAMESPACE_ID` with the id from step 2.

### 2b. Edge Worker → Cloudflare Workers

[`backend/edge/worker.js`](backend/edge/worker.js) implements the O(1) edge design:
every query reduces to a **deterministic address** (point → H3 cell id → KV/array
lookup; tile → PMTiles Hilbert id → R2 byte range; scenario → `hash(params)` → KV
delta) with no origin compute. It mirrors the FastAPI endpoint paths, so the
frontend works against either.

```bash
cd backend/edge
wrangler deploy            # → https://bharat-climate-twin-edge.<subdomain>.workers.dev
```

### 2c. Frontend → Cloudflare Pages

Deploy the Next.js dashboard to Pages and point it at the Worker via
`NEXT_PUBLIC_API_BASE`:

```bash
cd frontend
npm install && npm run build
# Connect the repo in the Cloudflare Pages dashboard (build command `npm run build`,
# project root `frontend/`), or push the build with Wrangler:
npx wrangler pages deploy .next --project-name bharat-climate-twin
```

Set the Pages environment variable so the dashboard reads from the edge Worker:

```
NEXT_PUBLIC_API_BASE = https://bharat-climate-twin-edge.<subdomain>.workers.dev
```

Leave it unset to ship the committed static JSON (an always-works offline fallback).

### 2d. Free-tier feasibility (verified 2025–2026)

| Platform | Role | Free tier | Verdict |
|---|---|---|---|
| **Cloudflare R2** | artifact / tile store | 10 GB-month, egress **FREE** | ✅ zero egress is the killer feature |
| **Cloudflare Workers** | edge API / tile range | ~100k req/day free | ✅ pair with R2 + KV |
| **Cloudflare Pages** | static / Next.js frontend | unlimited static requests, 500 builds/mo | ✅ best home for the UI |
| **Cloudflare KV / D1** | hot cache / metadata | ample free tiers | ✅ cell/scenario indexes |

---

## 3. Backend container hosting (alternatives)

The FastAPI service ([`backend/Dockerfile`](backend/Dockerfile)) is a portable
slim-Python image. It is **stateless** (artifacts baked in or mounted) and listens
on `:8000`, so any container host works:

| Host | How | Notes |
|---|---|---|
| **Google Cloud Run** | `gcloud run deploy bct-api --source . --port 8000` (or push the image) | scales to zero; 2M req/mo free; good for heavier `xarray`/GDAL/TiTiler work |
| **Fly.io** | `fly launch` then `fly deploy` (Dockerfile auto-detected) | global Anycast; small always-on VM |
| **Render** | new Web Service from repo → Docker, port `8000` | simplest CI-from-git |
| **Hugging Face Spaces** | Docker Space using `backend/Dockerfile` | public ML demo; pairs with ZeroGPU |

**Environment variables** (all optional — sensible defaults):

| Var | Default | Purpose |
|---|---|---|
| `BCT_DATA_DIR` | `../data/processed/sample` (image: `/app/data/processed/sample`) | where the artifacts are read from |
| `PORT` / `--port` | `8000` | listen port (set `--host 0.0.0.0` in containers) |

CORS is enabled for all origins for the demo. After deploy, point the frontend's
`NEXT_PUBLIC_API_BASE` at the service URL (append `/api` if you target the
namespaced endpoints).

---

## 4. Model inference

Per ARCHITECTURE §11.3, the **default and recommended** path is to **precompute
forecast/scenario layers offline** and serve them as static JSON / COG / Zarr —
fastest, cheapest, and most demo-reliable:

```bash
python -m models.train          # evaluates on held-out test years, writes metrics.json + forecast.json
python -m models.predict --leads 7
```

The artifacts then ship via R2/KV (§2a) exactly like the data fields. For **bespoke,
on-demand** high-fidelity what-if runs, run the ConvLSTM/U-Net (or a Tier-2
foundation model) on **Modal** or **Hugging Face ZeroGPU** in bursts and stream the
result back; the models train on CPU or a single GPU and degrade gracefully when no
DL library is present (numpy/stdlib tier always runs — see
[`models/README.md`](models/README.md)).

---

## 5. Data refresh & scheduling

The twin's "continuous update" heartbeat is realized by re-running the precompute
pipeline on a schedule and redeploying the artifacts. The hot path is read-only, so
a refresh is just: regenerate → upload to R2/KV → (artifacts are immutable + CDN-
cached, so clients pick up the new version on next fetch).

A minimal GitHub Actions cron:

```yaml
# .github/workflows/refresh.yml
name: refresh-climate-twin
on:
  schedule:
    - cron: "0 1 * * *"     # daily at 01:00 UTC
  workflow_dispatch: {}
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r pipeline/requirements.txt
      - run: python -m pipeline.run_pipeline --mode auto    # probe real sources, fall back to synthetic
      - run: python -m models.train                          # refresh metrics.json + forecast.json
      # Republish to R2 + KV (Wrangler) — secrets: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
      - run: npm i -g wrangler
      - run: |
          for f in metadata fields_daily climatology uncertainty scenarios sources metrics forecast; do
            wrangler r2 object put bct-artifacts/$f.json --file data/processed/sample/$f.json
          done
```

The same flow runs as `scripts/refresh_daily.sh` locally or as a Modal scheduled
function for GPU-backed refreshes. `--mode auto` keeps the system robust: it uses
real IMD/IMERG/ERA5-Land/MODIS/INSAT/CHIRPS where credentials and network are
available and transparently falls back to the synthetic generator otherwise, so the
refresh job never fails closed.

---

## Reference files

- [`backend/Dockerfile`](backend/Dockerfile) — FastAPI serving image (build from repo root)
- [`backend/edge/worker.js`](backend/edge/worker.js) + [`backend/edge/wrangler.toml`](backend/edge/wrangler.toml) — Cloudflare Worker (R2/KV bindings, deploy steps)
- `frontend/Dockerfile` — Next.js dashboard image (used by `docker-compose.yml`)
- `docker-compose.yml` — one-command local demo (backend + frontend)
- [`ARCHITECTURE.md`](ARCHITECTURE.md) §11 — full deployment & infrastructure topology
- [`CONTRACT.md`](CONTRACT.md) — the JSON serving-artifact contract both backends honour
