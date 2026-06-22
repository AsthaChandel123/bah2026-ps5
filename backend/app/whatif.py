"""Server-side what-if recompute — physics mirrored from ``frontend/lib/whatif.ts``.

The contract (ARCHITECTURE.md S8, CONTRACT.md scenarios.physics) is::

    tmax'     = tmax + dT
    tmin'     = tmin + dT
    rainfall' = rainfall * (1 + dP/100)
        ... and heavy-rain days (baseline value >= per-cell p90 of wet days) are
        additionally amplified by Clausius-Clapeyron:  * (1 + cc/100 * dT)
    onset_shift: roll the rainfall TIME axis by N days (positive = later
        monsoon, so day t shows what day (t - shift) used to be).

The transforms below are written to produce **bit-for-bit** the same numbers as
the TypeScript client (same clamping at 0, same modulo for the onset roll, same
p90 threshold definition), so an optimistic client preview and the server answer
agree. A numpy fast path is used when available; otherwise a pure-python path
produces identical results.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .data_store import HAVE_NUMPY, DataStore

if HAVE_NUMPY:  # pragma: no branch
    import numpy as np  # type: ignore


# Variables that are temperatures (offset by dT) vs rainfall (scaled/rolled).
TEMP_VARS = ("tmax", "tmin")


def _mod(n: int, m: int) -> int:
    """Positive modulo so the onset roll wraps correctly for negative shifts."""
    return ((n % m) + m) % m


def transform_rain_value(
    base_value: float,
    rain_pct: float,
    temp_offset: float,
    cc_pct_per_degc: float,
    heavy_threshold: float,
) -> float:
    """Apply the rainfall scenario transform to one baseline value.

    Mirrors ``transformRainValue`` in whatif.ts: linear %-scale, then a
    Clausius-Clapeyron multiplier on heavy-rain days (only when warming), then
    clamp to >= 0.
    """
    v = base_value * (1.0 + rain_pct / 100.0)
    if temp_offset != 0 and base_value >= heavy_threshold:
        v = v * (1.0 + (cc_pct_per_degc / 100.0) * temp_offset)
    return v if v > 0.0 else 0.0


# --------------------------------------------------------------------------- #
# Single-timestep field (for the map).
# --------------------------------------------------------------------------- #
def scenario_field_at_time(
    store: DataStore,
    variable: str,
    time_index: int,
    temp_offset: float,
    rain_pct: float,
    onset_shift: int,
) -> List[List[float]]:
    """Compute the scenario ``[lat][lon]`` grid for ONE timestep.

    Equivalent to ``scenarioFieldAtTime`` in whatif.ts.
    """
    if variable in TEMP_VARS:
        src = store.field_slice(variable, time_index)
        if temp_offset == 0:
            return [list(row) for row in src]
        return [[v + temp_offset for v in row] for row in src]

    # rainfall: onset roll selects the SOURCE day.
    src_day = _mod(time_index - int(onset_shift), store.ntime)
    src = store.field_slice("rainfall", src_day)
    if temp_offset == 0 and rain_pct == 0 and onset_shift == 0:
        return [list(row) for row in src]

    cc = store.cc_pct_per_degc()
    thr = store.heavy_rain_threshold_grid(store.heavy_rain_percentile())
    return [
        [
            transform_rain_value(src[i][j], rain_pct, temp_offset, cc, thr[i][j])
            for j in range(store.nlon)
        ]
        for i in range(store.nlat)
    ]


# --------------------------------------------------------------------------- #
# Single-cell full series (for the charts).
# --------------------------------------------------------------------------- #
def scenario_series_at_cell(
    store: DataStore,
    variable: str,
    i: int,
    j: int,
    temp_offset: float,
    rain_pct: float,
    onset_shift: int,
) -> Tuple[List[float], List[float]]:
    """Return ``(baseline, scenario)`` daily series for one cell.

    Equivalent to ``scenarioSeriesAtCell`` in whatif.ts.
    """
    if variable in TEMP_VARS:
        baseline = store.cell_series(variable, i, j)
        scenario = [b + temp_offset for b in baseline]
        return baseline, scenario

    rain = store.artifacts["fields_daily"]["rainfall"]
    cc = store.cc_pct_per_degc()
    thr = store.heavy_rain_threshold_grid(store.heavy_rain_percentile())[i][j]
    baseline = [rain[t][i][j] for t in range(store.ntime)]
    scenario = []
    for t in range(store.ntime):
        src_day = _mod(t - int(onset_shift), store.ntime)
        scenario.append(
            transform_rain_value(rain[src_day][i][j], rain_pct, temp_offset, cc, thr)
        )
    return baseline, scenario


# --------------------------------------------------------------------------- #
# Region-mean impact summary (numpy fast path + pure-python fallback).
# --------------------------------------------------------------------------- #
def compute_impact_summary(
    store: DataStore,
    variable: str,
    temp_offset: float,
    rain_pct: float,
    onset_shift: int,
) -> Dict[str, float]:
    """Region-mean impact of a scenario over the full year & grid.

    Mirrors ``computeImpactSummary`` in whatif.ts. For temperature the summary
    is the region/year-mean temperature and its uniform shift; for rainfall it
    is the region-mean seasonal total and the region-mean count of heavy-rain
    (>= p90) days, baseline vs scenario.
    """
    ncell = store.nlat * store.nlon
    onset_shift = int(onset_shift)

    if variable in TEMP_VARS:
        arr = store.numpy_field(variable)
        if HAVE_NUMPY and arr is not None:
            baseline_mean = float(arr.mean())
        else:
            fields = store.artifacts["fields_daily"][variable]
            total = sum(
                fields[t][i][j]
                for t in range(store.ntime)
                for i in range(store.nlat)
                for j in range(store.nlon)
            )
            baseline_mean = total / (store.ntime * ncell)
        return {
            "variable": variable,
            "baselineMeanTemp": baseline_mean,
            "scenarioMeanTemp": baseline_mean + temp_offset,
            "deltaMeanTemp": float(temp_offset),
        }

    # Rainfall: seasonal total (region-mean) + heavy-rain day counts.
    cc = store.cc_pct_per_degc()
    thr_grid = store.heavy_rain_threshold_grid(store.heavy_rain_percentile())

    rain_np = store.numpy_field("rainfall")
    if HAVE_NUMPY and rain_np is not None:
        return _impact_rain_numpy(
            store, rain_np, thr_grid, cc, temp_offset, rain_pct, onset_shift, ncell
        )

    rain = store.artifacts["fields_daily"]["rainfall"]
    base_total = scen_total = 0.0
    base_extreme = scen_extreme = 0
    for i in range(store.nlat):
        for j in range(store.nlon):
            cell_thr = thr_grid[i][j]
            finite = cell_thr != float("inf")
            for t in range(store.ntime):
                b = rain[t][i][j]
                base_total += b
                if finite and b >= cell_thr:
                    base_extreme += 1
                src_day = _mod(t - onset_shift, store.ntime)
                s = transform_rain_value(rain[src_day][i][j], rain_pct, temp_offset, cc, cell_thr)
                scen_total += s
                if finite and s >= cell_thr:
                    scen_extreme += 1
    return _assemble_rain_summary(
        base_total, scen_total, base_extreme, scen_extreme, ncell
    )


def _impact_rain_numpy(
    store: DataStore,
    rain: "np.ndarray",
    thr_grid: List[List[float]],
    cc: float,
    temp_offset: float,
    rain_pct: float,
    onset_shift: int,
    ncell: int,
) -> Dict[str, float]:
    """Vectorised rainfall impact summary (numerically identical to the loop)."""
    thr = np.asarray(thr_grid, dtype="float64")  # (nlat, nlon)
    finite = np.isfinite(thr)

    # Onset roll along the time axis (axis 0). np.roll with +onset_shift makes
    # day t pull from day (t - onset_shift), matching the TS mod() convention.
    rolled = np.roll(rain, onset_shift, axis=0)

    scen = rolled * (1.0 + rain_pct / 100.0)
    if temp_offset != 0:
        heavy = rolled >= thr[None, :, :]
        mult = np.where(heavy, 1.0 + (cc / 100.0) * temp_offset, 1.0)
        scen = scen * mult
    scen = np.where(scen > 0.0, scen, 0.0)

    base_total = float(rain.sum())
    scen_total = float(scen.sum())

    base_extreme = int(
        ((rain >= thr[None, :, :]) & finite[None, :, :]).sum()
    )
    scen_extreme = int(
        ((scen >= thr[None, :, :]) & finite[None, :, :]).sum()
    )
    return _assemble_rain_summary(
        base_total, scen_total, base_extreme, scen_extreme, ncell
    )


def _assemble_rain_summary(
    base_total: float,
    scen_total: float,
    base_extreme: int,
    scen_extreme: int,
    ncell: int,
) -> Dict[str, float]:
    """Build the rainfall impact dict (region-means), as in whatif.ts."""
    baseline_seasonal = base_total / ncell
    scenario_seasonal = scen_total / ncell
    delta = scenario_seasonal - baseline_seasonal
    return {
        "variable": "rainfall",
        "baselineSeasonalRain": baseline_seasonal,
        "scenarioSeasonalRain": scenario_seasonal,
        "deltaSeasonalRain": delta,
        "deltaSeasonalRainPct": (delta / baseline_seasonal * 100.0) if baseline_seasonal > 0 else 0.0,
        "baselineExtremeDays": base_extreme / ncell,
        "scenarioExtremeDays": scen_extreme / ncell,
        "deltaExtremeDays": (scen_extreme - base_extreme) / ncell,
    }
