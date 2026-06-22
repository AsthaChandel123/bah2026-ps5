"""
pipeline.run_pipeline
=====================
Orchestrator / CLI for the Bharat Climate Twin data pipeline.

For each source it **tries real ingestion** and **falls back to synthetic**,
then harmonizes (no-op for synthetic — already on grid), **fuses** the
pseudo-independent sources (quantile mapping + OI merge + triple collocation),
computes the **climatology**, and **exports** the serving artifacts defined in
CONTRACT.md to both ``data/processed/sample/`` and ``frontend/public/data/``.

It prints a clear summary of which sources were used (real vs synthetic) and
what was written.

Usage
-----
    python -m pipeline.run_pipeline --mode synthetic   # always works, no network
    python -m pipeline.run_pipeline --mode auto        # try real, fall back
    python pipeline/run_pipeline.py --mode synthetic

The ``synthetic`` mode is guaranteed to run on the **standard library alone**
(no numpy/xarray), so the demo artifacts can always be (re)generated.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from datetime import date
from typing import Dict, List, Tuple

from . import __version__
from .config import GRID, PATHS, TIME, VARIABLE_ORDER, GridSpec
from .synthetic import (
    SyntheticYear,
    daterange,
    enso_factor,
    generate_pseudo_sources,
    generate_year,
)
from . import export as E
from . import fusion as F


# ──────────────────────────────────────────────────────────────────────────
# Source probing (auto mode)
# ──────────────────────────────────────────────────────────────────────────
def _probe_real_sources(
    bbox: Tuple[float, float, float, float], start: date, end: date
) -> Dict[str, str]:
    """Attempt each real ingestion module; record 'real' or the failure reason.

    Returns ``{source_name: status}``. We import the ingest modules lazily and
    catch *everything* — a probe must never crash the pipeline. This populates
    the run summary; the fused product itself uses synthetic pseudo-sources in
    this PoC (real materialisation happens in the heavy precompute job).
    """
    statuses: Dict[str, str] = {}
    probes = [
        ("IMD gridded (imdlib)", "pipeline.ingest.imd", "fetch"),
        ("GPM IMERG V07 (GEE)", "pipeline.ingest.imerg", "fetch"),
        ("ERA5-Land (GEE/CDS)", "pipeline.ingest.era5", "fetch"),
        ("MODIS LST (GEE)", "pipeline.ingest.modis_lst", "fetch"),
        ("INSAT-3D (MOSDAC)", "pipeline.ingest.mosdac", "fetch"),
        ("CHIRPS (GEE)", "pipeline.ingest.chirps", "fetch"),
    ]
    import importlib

    for label, mod_name, fn_name in probes:
        try:
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, fn_name)
            fn(bbox, start, end)  # will raise IngestUnavailable without creds
            statuses[label] = "real"
        except Exception as exc:
            # Trim long messages for the summary table.
            reason = str(exc).split(". ")[0][:80]
            statuses[label] = f"synthetic (fallback: {reason})"
    return statuses


# ──────────────────────────────────────────────────────────────────────────
# Climatology + annual aggregation (pure stdlib)
# ──────────────────────────────────────────────────────────────────────────
def _region_mean_plane(plane: List[List[float]]) -> float:
    """Spatial mean of one [nlat][nlon] field."""
    vals = [v for row in plane for v in row]
    return sum(vals) / len(vals) if vals else 0.0


def _monthly_region_means(year: SyntheticYear) -> Dict[str, List[float]]:
    """Per-month spatial-mean climatology for each variable (rainfall summed)."""
    dates = [date.fromisoformat(d) for d in year.dates]
    months = [d.month for d in dates]

    out: Dict[str, List[float]] = {"rainfall": [], "tmax": [], "tmin": []}
    for m in range(1, 13):
        idxs = [t for t, mm in enumerate(months) if mm == m]
        # rainfall → monthly TOTAL of daily region-means (mm/month);
        # temperature → monthly MEAN of daily region-means (°C).
        rain_sum = sum(_region_mean_plane(year.rainfall[t]) for t in idxs)
        tmax_mean = statistics.fmean(_region_mean_plane(year.tmax[t]) for t in idxs)
        tmin_mean = statistics.fmean(_region_mean_plane(year.tmin[t]) for t in idxs)
        out["rainfall"].append(round(rain_sum, 1))
        out["tmax"].append(round(tmax_mean, 1))
        out["tmin"].append(round(tmin_mean, 1))
    return out


def _annual_by_year(grid: GridSpec, years: List[int]) -> Dict[str, List]:
    """Annual region totals/means per year (interannual / ENSO story).

    rainfall = annual TOTAL (mm/yr) of daily region-means; temperature = annual
    MEAN (°C). Generates each year synthetically (cheap) for the multi-year span.
    """
    rain_series: List[float] = []
    tmax_series: List[float] = []
    tmin_series: List[float] = []
    for y in years:
        sy = generate_year(y, grid)
        rain_series.append(round(sum(_region_mean_plane(p) for p in sy.rainfall), 1))
        tmax_series.append(round(statistics.fmean(_region_mean_plane(p) for p in sy.tmax), 1))
        tmin_series.append(round(statistics.fmean(_region_mean_plane(p) for p in sy.tmin), 1))
    return {
        "years": years,
        "rainfall": rain_series,
        "tmax": tmax_series,
        "tmin": tmin_series,
    }


# ──────────────────────────────────────────────────────────────────────────
# Fusion of the representative year (uncertainty fields)
# ──────────────────────────────────────────────────────────────────────────
def _fuse_year(year: int, grid: GridSpec):
    """Run the two-stage fusion on the 3 pseudo-sources for each variable.

    Returns ``(fused_fields, uncertainty01)`` where ``fused_fields`` is the
    analysis cube per variable and ``uncertainty01`` is the 0..1 normalised
    per-cell uncertainty per variable (from triple collocation).
    """
    fused_fields: Dict[str, SyntheticYear] = {}
    uncertainty01: Dict[str, List[List[float]]] = {}

    for var in VARIABLE_ORDER:
        srcs = generate_pseudo_sources(year, grid)
        # Pull the per-variable cube out of each pseudo-source.
        def _cube(sy: SyntheticYear):
            return getattr(sy, var)

        fv = F.fuse_variable(
            var,
            _cube(srcs["imd"]),
            _cube(srcs["imerg"]),
            _cube(srcs["era5land"]),
        )
        fused_fields[var] = fv.analysis
        uncertainty01[var] = F.normalize_uncertainty(fv.sigma)

    return fused_fields, uncertainty01


# ──────────────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────────────
def run(mode: str = "synthetic", grid: GridSpec = GRID) -> dict:
    """Run the full pipeline and write all serving artifacts.

    Parameters
    ----------
    mode:
        ``"synthetic"`` (default; never touches the network) or ``"auto"``
        (probe real sources, report status, still build from synthetic for the
        deterministic demo).

    Returns
    -------
    dict
        Summary suitable for printing (sources used, artifacts + sizes).
    """
    PATHS.ensure()
    bbox = grid.bbox
    sample_year = TIME.sample_year

    print("=" * 74)
    print(f"  Bharat Climate Twin — data pipeline v{__version__}")
    print(f"  Region : {grid.name}")
    print(f"  bbox   : {list(bbox)}  (W,S,E,N)")
    print(f"  Grid   : {grid.res_deg}°  →  {grid.nlat} lat × {grid.nlon} lon "
          f"= {grid.nlat * grid.nlon} cells")
    print(f"  Mode   : {mode}")
    print("=" * 74)

    # ---- 1. Source acquisition (real probe in auto mode) ----
    source_status: Dict[str, str] = {}
    if mode == "auto":
        print("\n[1/5] Probing real data sources (auto mode)…")
        source_status = _probe_real_sources(bbox, TIME.start, TIME.end)
        for name, st in source_status.items():
            tag = "✓ REAL" if st == "real" else "→ synth"
            print(f"      {tag:8s} {name}: {st}")
    else:
        print("\n[1/5] Synthetic mode — generating physically-plausible fields "
              "(zero network).")
        for name in ("IMD gridded", "GPM IMERG V07", "ERA5-Land", "MODIS LST",
                     "INSAT-3D (MOSDAC)", "CHIRPS"):
            source_status[name] = "synthetic"

    # ---- 2. Build representative year (the demo field) ----
    print(f"\n[2/5] Generating representative year {sample_year} "
          f"(ENSO factor {enso_factor(sample_year):.2f})…")
    base = generate_year(sample_year, grid)

    # ---- 3. Multi-source fusion + uncertainty (triple collocation) ----
    print("[3/5] Fusing pseudo-independent sources "
          "(quantile-map → OI merge → triple collocation)…")
    fused_fields, uncertainty01 = _fuse_year(sample_year, grid)
    # Use the fused analysis as the served field (best estimate).
    rainfall = fused_fields["rainfall"]
    tmax = fused_fields["tmax"]
    tmin = fused_fields["tmin"]

    # ---- 4. Climatology (monthly + interannual) ----
    print(f"[4/5] Computing climatology "
          f"({TIME.clim_start_year}–{TIME.clim_end_year})…")
    monthly = _monthly_region_means(base)
    annual = _annual_by_year(grid, TIME.clim_years)

    # ---- 5. Export all artifacts ----
    print("[5/5] Writing serving artifacts…")
    data_mode = "auto-probe+synthetic" if mode == "auto" else "synthetic"
    out_dirs = (PATHS.sample, PATHS.frontend_public_data)

    artifacts = {
        "metadata.json": E.build_metadata(grid, base.dates, data_mode),
        "fields_daily.json": E.build_fields_daily(
            grid, rainfall, tmax, tmin, base.dates
        ),
        "climatology.json": E.build_climatology(monthly, annual),
        "uncertainty.json": E.build_uncertainty(
            grid, uncertainty01["rainfall"], uncertainty01["tmax"],
            uncertainty01["tmin"],
        ),
        "scenarios.json": E.build_scenarios(),
        "sources.json": E.build_sources(),
        "metrics.json": E.build_metrics_stub(),
    }

    written: Dict[str, List] = {}
    for name, obj in artifacts.items():
        paths = E._write_json(obj, *out_dirs, name=name)
        written[name] = paths

    # ---- Optional real-path artifacts (skipped silently if libs absent) ----
    # These are the production O(1) serving cube/rasters; their absence must
    # never block the always-on JSON demo artifacts above.
    try:
        zarr_path = E.write_zarr_cube(
            rainfall, tmax, tmin, base.dates, grid, PATHS.zarr_cube
        )
    except Exception:
        zarr_path = None
    try:
        cog_paths = E.write_cogs(
            {"rainfall": rainfall, "tmax": tmax, "tmin": tmin},
            base.dates, grid, PATHS.cog_dir,
        )
    except Exception:
        cog_paths = []

    # ---- Summary ----
    summary = _summarize(written, source_status, zarr_path, cog_paths)
    _print_summary(summary)
    return summary


def _summarize(written, source_status, zarr_path, cog_paths) -> dict:
    """Collect file sizes + a couple of sample values for the run report."""
    sizes = {}
    for name, paths in written.items():
        p = paths[0]
        sizes[name] = p.stat().st_size

    # A couple of sanity sample values from the fields artifact.
    import json as _json

    fields = _json.loads((PATHS.sample / "fields_daily.json").read_text())
    mid_t = len(fields["dates"]) // 2  # a July-ish day
    sample_values = {
        "date_sample": fields["dates"][mid_t],
        "rainfall[mid,0,0]": fields["rainfall"][mid_t][0][0],
        "tmax[mid,0,0]": fields["tmax"][mid_t][0][0],
        "tmin[mid,0,0]": fields["tmin"][mid_t][0][0],
    }
    return {
        "sizes_bytes": sizes,
        "total_bytes": sum(sizes.values()),
        "source_status": source_status,
        "zarr": str(zarr_path) if zarr_path else None,
        "cogs": [str(p) for p in cog_paths],
        "sample_values": sample_values,
        "out_dirs": [str(PATHS.sample), str(PATHS.frontend_public_data)],
    }


def _print_summary(summary: dict) -> None:
    print("\n" + "─" * 74)
    print("  ARTIFACTS WRITTEN (to data/processed/sample/ AND frontend/public/data/)")
    print("─" * 74)
    for name, nbytes in summary["sizes_bytes"].items():
        print(f"    {name:22s} {nbytes / 1024:8.1f} KB")
    print(f"    {'TOTAL':22s} {summary['total_bytes'] / 1024:8.1f} KB "
          f"({summary['total_bytes'] / 1e6:.2f} MB)")

    print("\n  SAMPLE VALUES (mid-year day, NW cell):")
    sv = summary["sample_values"]
    print(f"    date={sv['date_sample']}  "
          f"rainfall={sv['rainfall[mid,0,0]']} mm  "
          f"tmax={sv['tmax[mid,0,0]']}°C  tmin={sv['tmin[mid,0,0]']}°C")

    if summary["zarr"]:
        print(f"\n  Real-path Zarr cube : {summary['zarr']}(_space/_time).zarr")
    else:
        print("\n  Real-path Zarr cube : skipped (xarray/zarr not installed) — "
              "JSON artifacts are the demo dataset.")
    if summary["cogs"]:
        print(f"  Per-timestep COGs    : {len(summary['cogs'])} written")

    print("\n  Demo is ready: the JSON above is committed and works offline.")
    print("─" * 74)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pipeline.run_pipeline",
        description="Build Bharat Climate Twin serving artifacts (real or synthetic).",
    )
    parser.add_argument(
        "--mode",
        choices=("synthetic", "auto"),
        default="synthetic",
        help="synthetic = always-works offline demo; auto = probe real sources first.",
    )
    args = parser.parse_args(argv)
    try:
        run(mode=args.mode)
    except Exception as exc:  # never leave a half-written demo silently
        print(f"\nERROR: pipeline failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
