"""What-if scenario endpoints — server-side recompute matching the frontend.

``POST /api/whatif`` recomputes the displayed field (and optionally a point's
series) under a scenario, applying the SAME physics as
``frontend/lib/whatif.ts`` (see ``app/whatif.py``), and returns an impact summary
whose keys match the client's ``ImpactSummary``. A ``GET`` alias is provided for
the ARCHITECTURE S10 ``/whatif?dT=&dP=&onset=`` convenience form.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..data_store import BASE_VARS, DataStore, get_store
from ..models import WhatIfRequest, WhatIfResponse, WhatIfSeries
from ..whatif import (
    compute_impact_summary,
    scenario_field_at_time,
    scenario_series_at_cell,
)

router = APIRouter(tags=["whatif"])


def _units_for(store: DataStore, var: str) -> str:
    meta = store.get_artifact("metadata") or {}
    return meta.get("variables", {}).get(var, {}).get("units", "")


def _run_whatif(store: DataStore, req: WhatIfRequest) -> WhatIfResponse:
    """Core recompute shared by the POST and GET handlers."""
    var = req.var or "rainfall"
    if var not in BASE_VARS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown var '{var}'. Expected one of {list(BASE_VARS)}.",
        )
    try:
        ti = store.resolve_time_index(req.date)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Date '{req.date}' not on time axis")

    baseline_field = store.field_slice(var, ti)
    scenario_field = scenario_field_at_time(
        store, var, ti, req.temp_offset, req.rain_pct, req.onset_shift
    )
    delta_field = [
        [scenario_field[i][j] - baseline_field[i][j] for j in range(store.nlon)]
        for i in range(store.nlat)
    ]

    impact = compute_impact_summary(
        store, var, req.temp_offset, req.rain_pct, req.onset_shift
    )

    series = None
    if req.lat is not None and req.lon is not None:
        i, j = store.nearest_cell(req.lat, req.lon)
        base, scen = scenario_series_at_cell(
            store, var, i, j, req.temp_offset, req.rain_pct, req.onset_shift
        )
        series = WhatIfSeries(
            cell_id=store.cell_id(i, j),
            i=i,
            j=j,
            lat=store.lats[i],
            lon=store.lons[j],
            baseline=base,
            scenario=scen,
        )

    return WhatIfResponse(
        params={
            "temp_offset": float(req.temp_offset),
            "rain_pct": float(req.rain_pct),
            "onset_shift": float(req.onset_shift),
        },
        var=var,
        date=store.dates[ti],
        time_index=ti,
        units=_units_for(store, var),
        match="recomputed",
        lats=store.lats,
        lons=store.lons,
        baseline_field=baseline_field,
        scenario_field=scenario_field,
        delta_field=delta_field,
        impact=impact,
        series=series,
    )


@router.post(
    "/api/whatif",
    response_model=WhatIfResponse,
    summary="Recompute a scenario field/series + impact summary (server-side)",
)
def post_whatif(req: WhatIfRequest, store: DataStore = Depends(get_store)):
    """Apply ``{temp_offset, rain_pct, onset_shift}`` and return the recomputed
    field, the baseline, their delta, and an impact summary. Math is identical to
    ``frontend/lib/whatif.ts`` so the client preview and server agree."""
    return _run_whatif(store, req)


@router.get(
    "/api/whatif",
    response_model=WhatIfResponse,
    summary="GET convenience alias (ARCHITECTURE S10 dT/dP/onset form)",
)
def get_whatif(
    temp_offset: float = Query(0.0, alias="temp_offset"),
    rain_pct: float = Query(0.0, alias="rain_pct"),
    onset_shift: int = Query(0, alias="onset_shift"),
    dT: float | None = Query(None, description="Alias for temp_offset"),
    dP: float | None = Query(None, description="Alias for rain_pct"),
    onset: int | None = Query(None, description="Alias for onset_shift"),
    var: str | None = Query(None),
    date: str | None = Query(None),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
    store: DataStore = Depends(get_store),
):
    """GET form accepting both ``temp_offset/rain_pct/onset_shift`` and the
    short ``dT/dP/onset`` aliases from ARCHITECTURE S10.2."""
    req = WhatIfRequest(
        temp_offset=dT if dT is not None else temp_offset,
        rain_pct=dP if dP is not None else rain_pct,
        onset_shift=onset if onset is not None else onset_shift,
        var=var,
        date=date,
        lat=lat,
        lon=lon,
    )
    return _run_whatif(store, req)
