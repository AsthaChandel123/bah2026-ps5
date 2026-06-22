"""Bharat Climate Twin — O(1) serving API (FastAPI).

A fast, read-only service that preloads the precomputed serving artifacts from
``data/processed/sample/`` into memory **once** at startup (the pilot grid is
tiny -> everything fits in RAM) and answers every query in O(1) via direct
index / dict lookups. No per-request file I/O, no scans.

It exposes BOTH:
  * the exact artifact shapes the frontend already fetches
    (``frontend/lib/api.ts``) so swapping ``NEXT_PUBLIC_API_BASE`` to this
    backend "just works"; and
  * the richer query / scaling endpoints from ARCHITECTURE.md S10
    (``/api/fields``, ``/api/point``, ``/api/timeseries``, ``/api/whatif`` ...).

Run::

    uvicorn app.main:app --reload --port 8000

Then browse the interactive docs at ``http://localhost:8000/docs``.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from .data_store import STORE, DataStore, get_store, HAVE_H3, HAVE_NUMPY
from .models import HealthResponse
from .routes import artifacts, query, tiles, whatif_routes

API_VERSION = "1.0"

logger = logging.getLogger("bct.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load every artifact into the module-level store exactly once at startup.

    All O(n) work (parsing the JSON cube, building the H3 index and the
    per-cell p90 grid) happens here, so the hot request path is pure O(1)
    lookups.
    """
    t0 = time.perf_counter()
    STORE.load()
    # Warm the heavy-rain threshold grid so the first what-if call is also O(1).
    STORE.heavy_rain_threshold_grid(STORE.heavy_rain_percentile())
    dt = (time.perf_counter() - t0) * 1000.0
    logger.info(
        "Loaded %d artifacts from %s in %.1f ms (grid %dx%dx%d, h3=%s, numpy=%s)",
        len(STORE.artifacts),
        STORE.data_dir,
        dt,
        STORE.ntime,
        STORE.nlat,
        STORE.nlon,
        HAVE_H3,
        HAVE_NUMPY,
    )
    yield
    # Nothing to tear down — the store is plain in-memory data.


app = FastAPI(
    title="Bharat Climate Twin — O(1) Serving API",
    description=(
        "Constant-time serving of a precomputed, uncertainty-aware digital twin "
        "of India's climate (rainfall + temperature) for the Marathwada pilot. "
        "Artifacts are preloaded into RAM at startup and served via direct "
        "index / H3-dict lookups (ARCHITECTURE.md S7). Mirrors the JSON contract "
        "in CONTRACT.md and frontend/lib/api.ts."
    ),
    version=API_VERSION,
    lifespan=lifespan,
)

# CORS — allow the Next.js dashboard (any origin for the PoC / demo).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers.
app.include_router(artifacts.router)
app.include_router(query.router)
app.include_router(whatif_routes.router)
app.include_router(tiles.router)


@app.get("/", tags=["meta"], summary="Service banner + endpoint index")
def root():
    """Human-friendly index of the available endpoints."""
    return {
        "service": "bharat-climate-twin-api",
        "version": API_VERSION,
        "docs": "/docs",
        "health": "/api/health",
        "endpoints": {
            "artifacts": [
                "/api/metadata",
                "/api/fields_daily",
                "/api/climatology",
                "/api/uncertainty",
                "/api/scenarios",
                "/api/sources",
                "/api/metrics",
            ],
            "query": [
                "/api/fields?var=&date=",
                "/api/point?lat=&lon=",
                "/api/timeseries?lat=&lon=&var=",
                "/api/forecast",
                "/api/scenarios/list",
            ],
            "whatif": ["POST /api/whatif", "GET /api/whatif?temp_offset=&rain_pct=&onset_shift="],
            "tiles": ["/api/tiles/{z}/{x}/{y}.png (stub -> PMTiles/TiTiler)"],
        },
    }


@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["meta"],
    summary="Liveness/readiness probe + store diagnostics",
)
def health(store: DataStore = Depends(get_store)):
    """Return store status + grid/H3 diagnostics for monitoring."""
    s = store.summary()
    return HealthResponse(
        status="ok" if s["loaded"] else "loading",
        version=API_VERSION,
        loaded=s["loaded"],
        artifacts=s["artifacts"],
        grid=s["grid"],
        cells=s["cells"],
        h3=s["h3"],
        numpy=s["numpy"],
    )
