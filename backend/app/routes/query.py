"""Richer query / scaling endpoints (ARCHITECTURE.md S10).

All lookups are O(1) in the size of the dataset:

* ``/api/fields``      -> one map slice; date->index dict + direct array index.
* ``/api/point``       -> closed-form (lat,lon)->(i,j); pulls the cell's series.
* ``/api/timeseries``  -> same O(1) addressing, single variable, with bands.
* ``/api/forecast``    -> served only if ``forecast.json`` exists.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from ..data_store import BASE_VARS, DataStore, get_store
from ..models import (
    FieldSliceResponse,
    ForecastResponse,
    PointResponse,
    PointSeriesVar,
    ScenarioListItem,
    TimeseriesResponse,
)

router = APIRouter(tags=["query"])


def _units_for(store: DataStore, var: str) -> str:
    meta = store.get_artifact("metadata") or {}
    return meta.get("variables", {}).get(var, {}).get("units", "")


def _check_var(var: str) -> None:
    if var not in BASE_VARS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown var '{var}'. Expected one of {list(BASE_VARS)}.",
        )


@router.get(
    "/api/fields",
    response_model=FieldSliceResponse,
    summary="Single-timestep grid slice for one variable (O(1))",
)
def get_field_slice(
    var: str = Query("rainfall", description="rainfall | tmax | tmin"),
    date: str | None = Query(None, description="ISO date; default = last day"),
    store: DataStore = Depends(get_store),
):
    """Return the ``[lat][lon]`` grid for ``var`` on ``date``.

    Addressing: ``date -> time_index`` via a prebuilt dict, then a direct index
    into the in-memory cube. No scan.
    """
    _check_var(var)
    try:
        ti = store.resolve_time_index(date)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Date '{date}' not on time axis")
    return FieldSliceResponse(
        var=var,
        date=store.dates[ti],
        time_index=ti,
        units=_units_for(store, var),
        lats=store.lats,
        lons=store.lons,
        values=store.field_slice(var, ti),
    )


@router.get(
    "/api/point",
    response_model=PointResponse,
    summary="Nearest cell: full daily series for all vars + uncertainty + climatology",
)
def get_point(
    lat: float = Query(..., description="Latitude (deg N)"),
    lon: float = Query(..., description="Longitude (deg E)"),
    store: DataStore = Depends(get_store),
):
    """Resolve ``(lat, lon)`` to its nearest grid cell in O(1) and return that
    cell's full daily series for every variable, its static uncertainty, and the
    region climatology for chart context.
    """
    i, j = store.nearest_cell(lat, lon)
    series = {
        var: PointSeriesVar(
            units=_units_for(store, var),
            values=store.cell_series(var, i, j),
            uncertainty=store.cell_uncertainty(var, i, j),
        )
        for var in BASE_VARS
    }
    return PointResponse(
        cell_id=store.cell_id(i, j),
        i=i,
        j=j,
        lat=store.lats[i],
        lon=store.lons[j],
        query_lat=lat,
        query_lon=lon,
        dates=store.dates,
        series=series,
        climatology=store.get_artifact("climatology"),
    )


@router.get(
    "/api/timeseries",
    response_model=TimeseriesResponse,
    summary="Full series at a cell for one variable (with uncertainty bands)",
)
def get_timeseries(
    lat: float = Query(..., description="Latitude (deg N)"),
    lon: float = Query(..., description="Longitude (deg E)"),
    var: str = Query("rainfall", description="rainfall | tmax | tmin"),
    start: str | None = Query(None, description="ISO start date (inclusive)"),
    end: str | None = Query(None, description="ISO end date (inclusive)"),
    store: DataStore = Depends(get_store),
):
    """Return ``t`` / ``value`` for a cell, plus ``lower`` / ``upper`` bands.

    The bands approximate the conformal interval of ARCHITECTURE S10.2 by
    scaling the static per-cell uncertainty (0..1) into the variable's range.
    """
    _check_var(var)
    i, j = store.nearest_cell(lat, lon)
    full = store.cell_series(var, i, j)

    # Optional date window via O(1) date->index lookups.
    lo_idx = 0
    hi_idx = store.ntime - 1
    if start:
        s = store.date_to_index(start)
        if s is None:
            raise HTTPException(status_code=404, detail=f"start '{start}' not on time axis")
        lo_idx = s
    if end:
        e = store.date_to_index(end)
        if e is None:
            raise HTTPException(status_code=404, detail=f"end '{end}' not on time axis")
        hi_idx = e
    if lo_idx > hi_idx:
        raise HTTPException(status_code=400, detail="start is after end")

    t = store.dates[lo_idx : hi_idx + 1]
    value = full[lo_idx : hi_idx + 1]

    # Build uncertainty bands. Static uncertainty is 0..1; scale into a sensible
    # absolute band using the variable's display range from metadata.
    unc01 = store.cell_uncertainty(var, i, j) or 0.0
    meta_var = (store.get_artifact("metadata") or {}).get("variables", {}).get(var, {})
    span = float(meta_var.get("vmax", 1.0)) - float(meta_var.get("vmin", 0.0))
    half_band = unc01 * span * 0.5
    lower: List[float] = []
    upper: List[float] = []
    for v in value:
        lo = v - half_band
        if var == "rainfall" and lo < 0:
            lo = 0.0
        lower.append(round(lo, 3))
        upper.append(round(v + half_band, 3))

    return TimeseriesResponse(
        cell_id=store.cell_id(i, j),
        i=i,
        j=j,
        lat=store.lats[i],
        lon=store.lons[j],
        var=var,
        unit=_units_for(store, var),
        t=t,
        value=value,
        lower=lower,
        upper=upper,
    )


@router.get(
    "/api/scenarios/list",
    response_model=List[ScenarioListItem],
    summary="Canonical scenario library as a flat list (ARCHITECTURE S10)",
)
def list_scenarios(store: DataStore = Depends(get_store)):
    """Return the scenario presets as ``[{id, label, params}]``.

    (The full ``scenarios.json`` — controls + physics + presets — is at
    ``/api/scenarios``; this is the S10 list-shaped convenience view.)
    """
    scen = store.get_artifact("scenarios") or {}
    out: List[ScenarioListItem] = []
    for p in scen.get("presets", []):
        out.append(
            ScenarioListItem(
                id=p["id"],
                label=p.get("label", p["id"]),
                params={
                    "temp_offset": p.get("temp_offset", 0),
                    "rain_pct": p.get("rain_pct", 0),
                    "onset_shift": p.get("onset_shift", 0),
                },
            )
        )
    return out


@router.get(
    "/api/forecast",
    response_model=ForecastResponse,
    summary="Latest AI forecast frame (served only if forecast.json present)",
)
def get_forecast(store: DataStore = Depends(get_store)):
    """Return ``forecast.json`` if the models worker has produced it.

    When absent we return ``available: false`` with a clear message and HTTP 200
    so the dashboard can gracefully hide the panel (rather than erroring).
    """
    fc = store.get_artifact("forecast")
    if fc is None:
        return ForecastResponse(
            available=False,
            message=(
                "No forecast.json present yet. It is produced by the models "
                "worker and will be served here once added to the data dir."
            ),
        )
    return ForecastResponse(available=True, forecast=fc)
