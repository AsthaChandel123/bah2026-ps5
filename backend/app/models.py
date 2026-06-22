"""Pydantic response models for the Bharat Climate Twin API.

These typed models document the **richer** query / scaling endpoints from
ARCHITECTURE.md S10 (``/api/point``, ``/api/timeseries``, ``/api/fields``,
``/api/whatif`` ...). The raw artifact endpoints (``/api/metadata``,
``/api/fields_daily`` ...) are returned verbatim from the in-memory store so
their shapes are byte-identical to ``CONTRACT.md`` / ``frontend/lib/types.ts``;
wrapping those in pydantic would risk drift, so they are served as-is.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness / readiness probe payload."""

    status: str = Field(examples=["ok"])
    service: str = "bharat-climate-twin-api"
    version: str
    loaded: bool
    artifacts: List[str]
    grid: Dict[str, float]
    cells: int
    h3: Dict[str, object]
    numpy: bool


class FieldSliceResponse(BaseModel):
    """A single-timestep grid slice for one variable (O(1) lookup)."""

    var: str = Field(description="rainfall | tmax | tmin")
    date: str
    time_index: int
    units: str
    lats: List[float]
    lons: List[float]
    values: List[List[float]] = Field(description="[lat][lon] grid, S->N, W->E")


class PointSeriesVar(BaseModel):
    """Per-variable daily series + static uncertainty at a grid cell."""

    units: str
    values: List[float]
    uncertainty: Optional[float] = Field(
        default=None, description="Static per-cell uncertainty (0..1)"
    )


class PointResponse(BaseModel):
    """Nearest grid cell's full daily series for all vars + climatology.

    Backs ``GET /api/point?lat=&lon=`` — a single O(1) index lookup returns the
    cell address, every variable's time series, that cell's uncertainty, and the
    region climatology for context.
    """

    cell_id: str = Field(description="H3 res-4 id (or synthetic fallback)")
    i: int
    j: int
    lat: float = Field(description="Cell-centre latitude")
    lon: float = Field(description="Cell-centre longitude")
    query_lat: float
    query_lon: float
    dates: List[str]
    series: Dict[str, PointSeriesVar]
    climatology: Optional[dict] = None


class TimeseriesResponse(BaseModel):
    """Full (or date-windowed) series at a cell for one variable.

    Mirrors the ARCHITECTURE S10.2 ``/timeseries`` shape: ``t`` / ``value`` plus
    conformal ``lower`` / ``upper`` bands derived from the static uncertainty.
    """

    cell_id: str
    i: int
    j: int
    lat: float
    lon: float
    var: str
    unit: str
    t: List[str]
    value: List[float]
    lower: List[float]
    upper: List[float]


class WhatIfRequest(BaseModel):
    """Request body for ``POST /api/whatif`` (server-side recompute)."""

    temp_offset: float = Field(0.0, description="dT in degC, added to tmax/tmin")
    rain_pct: float = Field(0.0, description="dP in %, scales rainfall totals")
    onset_shift: int = Field(0, description="Monsoon onset shift in days (rolls time axis)")
    var: Optional[str] = Field(
        default=None, description="rainfall|tmax|tmin; default rainfall"
    )
    date: Optional[str] = Field(
        default=None, description="ISO date for the returned map field; default last day"
    )
    lat: Optional[float] = Field(default=None, description="Optional point for a series")
    lon: Optional[float] = Field(default=None, description="Optional point for a series")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"temp_offset": 2.0, "rain_pct": -20.0, "onset_shift": 10, "var": "rainfall"}
            ]
        }
    }


class WhatIfSeries(BaseModel):
    """Optional per-cell baseline-vs-scenario series in a what-if response."""

    cell_id: str
    i: int
    j: int
    lat: float
    lon: float
    baseline: List[float]
    scenario: List[float]


class WhatIfResponse(BaseModel):
    """Recomputed field/series + impact summary for a scenario.

    Backs ``POST /api/whatif`` (and the ``GET`` convenience alias). The impact
    summary keys match ``frontend/lib/whatif.ts::ImpactSummary`` so the client
    and server agree on the headline numbers.
    """

    params: Dict[str, float]
    var: str
    date: str
    time_index: int
    units: str
    match: str = Field(default="recomputed", description="recomputed | library | interpolated")
    lats: List[float]
    lons: List[float]
    baseline_field: List[List[float]]
    scenario_field: List[List[float]]
    delta_field: List[List[float]]
    # impact mirrors frontend ImpactSummary: a "variable" string + numeric deltas.
    impact: Dict[str, Any]
    series: Optional[WhatIfSeries] = None


class ScenarioListItem(BaseModel):
    """One canonical scenario from the library (ARCHITECTURE S10 ``/scenarios``)."""

    id: str
    label: str
    params: Dict[str, float]


class ForecastResponse(BaseModel):
    """Forecast payload wrapper (served only if ``forecast.json`` is present)."""

    available: bool
    message: Optional[str] = None
    forecast: Optional[dict] = None
