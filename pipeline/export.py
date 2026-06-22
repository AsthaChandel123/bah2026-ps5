"""
pipeline.export
===============
Write the twin's serving artifacts.

Two output families (ARCHITECTURE.md §7, §4.2; CONTRACT.md):

* **Always path (pure standard library)** — the JSON serving artifacts that ARE
  the offline demo dataset (``metadata.json``, ``fields_daily.json``,
  ``climatology.json``, ``uncertainty.json``, ``scenarios.json``, ``sources.json``,
  ``metrics.json``). These are written to BOTH ``data/processed/sample/`` and
  ``frontend/public/data/`` and are committed to the repo. **No numpy needed.**

* **Real path (optional, needs xarray/zarr/rioxarray)** — a dual-chunked Zarr
  cube and per-timestep COGs for the production O(1) serving layer. Guarded so
  its absence never blocks the JSON artifacts.

Every writer is deterministic and rounds values per the contract.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .config import (
    ARTIFACTS,
    CLAUSIUS_CLAPEYRON_PCT_PER_DEGC,
    CONTRACT_VERSION,
    DATASETS,
    GRID,
    H3,
    TIME,
    VARIABLE_ORDER,
    VARIABLES,
    GridSpec,
)
from .synthetic import Cube, SyntheticYear


# ──────────────────────────────────────────────────────────────────────────
# JSON helpers
# ──────────────────────────────────────────────────────────────────────────
def _write_json(obj: dict, *dirs: Path, name: str) -> List[Path]:
    """Write ``obj`` as compact JSON to ``name`` in each directory in ``dirs``."""
    written: List[Path] = []
    payload = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_text(payload, encoding="utf-8")
        written.append(p)
    return written


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ──────────────────────────────────────────────────────────────────────────
# metadata.json
# ──────────────────────────────────────────────────────────────────────────
def build_metadata(
    grid: GridSpec,
    dates: List[str],
    data_mode: str,
) -> dict:
    """Assemble ``metadata.json`` (region, grid, time axis, variable display)."""
    return {
        "region": grid.name,
        "bbox": list(grid.bbox),
        "crs": "EPSG:4326",
        "grid": {
            "res_deg": grid.res_deg,
            "nlat": grid.nlat,
            "nlon": grid.nlon,
            "lats": grid.lats,
            "lons": grid.lons,
        },
        "time": {
            "freq": "daily",
            "start": dates[0],
            "end": dates[-1],
            "n": len(dates),
            "dates": dates,
        },
        "variables": {
            **{
                v.key: {
                    "long_name": v.long_name,
                    # `label` is a frontend-friendly alias of long_name (the
                    # Next.js dashboard's Legend/LayerPanel read
                    # `variables.<v>.label`); we ship both so the artifact
                    # satisfies the contract AND the UI.
                    "label": v.long_name,
                    "units": v.units,
                    "cmap": v.cmap,
                    "vmin": v.vmin,
                    "vmax": v.vmax,
                }
                for v in (VARIABLES[k] for k in VARIABLE_ORDER)
            },
            # Uncertainty is a first-class visualization layer (Design Principle
            # P4). It is a derived 0..1 field (see uncertainty.json), surfaced
            # here so the dashboard's Legend can render the uncertainty colormap.
            "uncertainty": {
                "long_name": "Per-pixel uncertainty (triple-collocation, 0..1)",
                "label": "Uncertainty",
                "units": "0..1",
                "cmap": "uncertainty",
                "vmin": 0.0,
                "vmax": 1.0,
            },
        },
        "h3": {"res_map": H3.res_map, "res_region": H3.res_region},
        "generated": _now_iso(),
        "data_mode": data_mode,
        "version": CONTRACT_VERSION,
    }


# ──────────────────────────────────────────────────────────────────────────
# fields_daily.json
# ──────────────────────────────────────────────────────────────────────────
def build_fields_daily(
    grid: GridSpec,
    rainfall: Cube,
    tmax: Cube,
    tmin: Cube,
    dates: List[str],
) -> dict:
    """Assemble ``fields_daily.json`` — one representative year of daily fields."""
    return {
        "dates": dates,
        "lats": grid.lats,
        "lons": grid.lons,
        "rainfall": rainfall,
        "tmax": tmax,
        "tmin": tmin,
    }


# ──────────────────────────────────────────────────────────────────────────
# climatology.json
# ──────────────────────────────────────────────────────────────────────────
def build_climatology(
    monthly_region_mean: Dict[str, List[float]],
    annual_by_year: Dict[str, List],
) -> dict:
    """Assemble ``climatology.json`` (monthly region means + annual-by-year)."""
    return {
        "months": list(range(1, 13)),
        "region_mean": {
            "rainfall": monthly_region_mean["rainfall"],
            "tmax": monthly_region_mean["tmax"],
            "tmin": monthly_region_mean["tmin"],
        },
        "annual_by_year": annual_by_year,
    }


# ──────────────────────────────────────────────────────────────────────────
# uncertainty.json
# ──────────────────────────────────────────────────────────────────────────
def build_uncertainty(
    grid: GridSpec,
    rainfall: List[List[float]],
    tmax: List[List[float]],
    tmin: List[List[float]],
) -> dict:
    """Assemble ``uncertainty.json`` (per-cell 0..1 fields from triple collocation)."""
    return {
        "lats": grid.lats,
        "lons": grid.lons,
        "rainfall": rainfall,
        "tmax": tmax,
        "tmin": tmin,
    }


# ──────────────────────────────────────────────────────────────────────────
# scenarios.json  (what-if controls + physics + presets)
# ──────────────────────────────────────────────────────────────────────────
def build_scenarios() -> dict:
    """Assemble ``scenarios.json`` — the what-if engine's control/physics spec."""
    return {
        "controls": {
            "temp_offset": {
                "label": "Temperature offset",
                "unit": "°C",
                "min": -2,
                "max": 5,
                "step": 0.5,
                "default": 0,
            },
            "rain_pct": {
                "label": "Rainfall change",
                "unit": "%",
                "min": -50,
                "max": 50,
                "step": 5,
                "default": 0,
            },
            "onset_shift": {
                "label": "Monsoon onset shift",
                "unit": "days",
                "min": -30,
                "max": 30,
                "step": 5,
                "default": 0,
            },
        },
        "physics": {
            "clausius_clapeyron_pct_per_degC": CLAUSIUS_CLAPEYRON_PCT_PER_DEGC,
            "notes": (
                "ΔT adds to tmax/tmin; rain_pct scales totals; CC amplifies "
                "heavy-rain (>p90) intensity by 7%/°C; onset_shift rolls the "
                "monsoon seasonal cycle"
            ),
        },
        "presets": [
            {"id": "baseline", "label": "Baseline",
             "temp_offset": 0, "rain_pct": 0, "onset_shift": 0},
            {"id": "warming_2c", "label": "+2 °C warming",
             "temp_offset": 2, "rain_pct": 0, "onset_shift": 0},
            {"id": "weak_monsoon", "label": "Weak monsoon (El Niño-like)",
             "temp_offset": 1, "rain_pct": -20, "onset_shift": 10},
            {"id": "strong_monsoon", "label": "Strong monsoon (La Niña-like)",
             "temp_offset": 0.5, "rain_pct": 25, "onset_shift": -5},
        ],
    }


# ──────────────────────────────────────────────────────────────────────────
# sources.json  (the 30+ Data Sources panel)
# ──────────────────────────────────────────────────────────────────────────
def build_sources() -> dict:
    """Assemble ``sources.json`` from the dataset registry (≥30 entries)."""
    return {
        "count": len(DATASETS),
        "sources": [
            {
                "name": d.name,
                "type": d.type,
                "role": d.role,
                "res": d.res,
                "provider": d.provider,
                "access": d.access,
            }
            for d in DATASETS
        ],
    }


# ──────────────────────────────────────────────────────────────────────────
# metrics.json  (stub — populated later by the models worker)
# ──────────────────────────────────────────────────────────────────────────
def build_metrics_stub() -> dict:
    """Assemble the ``metrics.json`` stub the frontend reads before models exist."""
    return {
        "models": [],
        "ensemble": {},
        "note": "populated by model training",
    }


# ──────────────────────────────────────────────────────────────────────────
# Real path — dual-chunked Zarr cube + per-timestep COGs (optional)
# ──────────────────────────────────────────────────────────────────────────
def write_zarr_cube(
    rainfall: Cube,
    tmax: Cube,
    tmin: Cube,
    dates: List[str],
    grid: GridSpec,
    out_path: Path,
) -> Optional[Path]:
    """Write the dual-chunked Zarr cube (ARCHITECTURE.md §7.3). Requires xarray.

    Stores BOTH a space-chunked layout (one daily field per chunk, for map
    slices) and a time-chunked layout (one cell's full series per chunk, for
    point time-series). Returns the path, or ``None`` if xarray/zarr are absent.
    """
    try:
        import numpy as np
        import pandas as pd
        import xarray as xr
    except Exception:
        return None  # offline-demo machine: skip silently, JSON artifacts suffice

    ntime = len(dates)
    nlat, nlon = grid.shape
    ds = xr.Dataset(
        {
            "rainfall": (("time", "lat", "lon"), np.asarray(rainfall)),
            "tmax": (("time", "lat", "lon"), np.asarray(tmax)),
            "tmin": (("time", "lat", "lon"), np.asarray(tmin)),
        },
        coords={
            "time": pd.to_datetime(dates),
            "lat": np.asarray(grid.lats),
            "lon": np.asarray(grid.lons),
        },
    )
    ds["rainfall"].attrs.update(units="mm/day")
    ds["tmax"].attrs.update(units="degC")
    ds["tmin"].attrs.update(units="degC")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    space = out_path.with_name(out_path.stem + "_space.zarr")
    time = out_path.with_name(out_path.stem + "_time.zarr")

    # Set chunk shapes via per-variable ``encoding`` rather than ``.chunk()`` so
    # we do NOT require dask (the arrays stay plain numpy). This realises the
    # dual-chunked layout from ARCHITECTURE.md §7.3:
    #   * space-chunked (map slices) : (time=1, lat=all, lon=all)
    #   * time-chunked (point series): (time=all, small lat/lon block)
    space_chunks = (1, nlat, nlon)
    time_chunks = (ntime, min(8, nlat), min(8, nlon))
    try:
        ds.to_zarr(
            str(space), mode="w",
            encoding={v: {"chunks": space_chunks} for v in ds.data_vars},
        )
        ds.to_zarr(
            str(time), mode="w",
            encoding={v: {"chunks": time_chunks} for v in ds.data_vars},
        )
    except Exception:
        # zarr/dask/codec issues must never block the JSON demo artifacts.
        return None
    return out_path


def write_cogs(
    field_by_var: Dict[str, Cube],
    dates: List[str],
    grid: GridSpec,
    out_dir: Path,
    max_timesteps: int = 5,
) -> List[Path]:
    """Write per-timestep Cloud-Optimized GeoTIFFs via rioxarray (optional).

    Writes up to ``max_timesteps`` representative dates per variable (the demo
    bakes a small set; the national job writes all). Returns the COG paths, or
    an empty list if rioxarray/rasterio are absent.
    """
    try:
        import numpy as np
        import rioxarray  # noqa: F401
        import xarray as xr
    except Exception:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    idxs = list(range(0, len(dates), max(1, len(dates) // max_timesteps)))[:max_timesteps]
    for var, cube in field_by_var.items():
        for t in idxs:
            da = xr.DataArray(
                np.asarray(cube[t]),
                dims=("lat", "lon"),
                coords={"lat": np.asarray(grid.lats), "lon": np.asarray(grid.lons)},
                name=var,
            )
            da = da.rio.write_crs("EPSG:4326")
            p = out_dir / f"{var}_{dates[t]}.tif"
            da.rio.to_raster(
                str(p), driver="COG", compress="DEFLATE",
                overview_resampling="average",
            )
            paths.append(p)
    return paths


__all__ = [
    "build_metadata",
    "build_fields_daily",
    "build_climatology",
    "build_uncertainty",
    "build_scenarios",
    "build_sources",
    "build_metrics_stub",
    "write_zarr_cube",
    "write_cogs",
    "_write_json",
]
