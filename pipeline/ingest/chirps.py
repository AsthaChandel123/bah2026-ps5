"""
pipeline.ingest.chirps
======================
CHIRPS — station-blended satellite rainfall, valuable in transitional climate
zones (ARCHITECTURE.md §4.1 #12; research/01 §3, research/06 §4.1).

Access via Google Earth Engine:
    v2 daily : ``UCSB-CHG/CHIRPS/DAILY``     band ``precipitation`` (mm/day, 0.05°)
    v3 daily : ``UCSB-CHC/CHIRPS/V3/DAILY_SAT`` (IMERG-based NRT)
               ``UCSB-CHC/CHIRPS/V3/DAILY_RNL`` (ERA5 reanalysis-blended)

⚠️ Independence caveat (ARCHITECTURE.md §4.3): CHIRPS v3 daily disaggregation
*uses* IMERG-Late, so CHIRPS-v3 and IMERG must NOT be treated as independent
triple-collocation members. v2 is safer for cross-validation.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple

from . import IngestUnavailable, require

GEE_V2 = "UCSB-CHG/CHIRPS/DAILY"
GEE_V3_SAT = "UCSB-CHC/CHIRPS/V3/DAILY_SAT"
GEE_V3_RNL = "UCSB-CHC/CHIRPS/V3/DAILY_RNL"
GEE_BAND = "precipitation"


def fetch(
    bbox: Tuple[float, float, float, float],
    start: date,
    end: date,
    asset: str = GEE_V2,
    gee_project: str | None = None,
):
    """Fetch daily CHIRPS rainfall (mm/day) over ``bbox`` from GEE.

    Parameters
    ----------
    bbox:
        (W, S, E, N) pilot region.
    start, end:
        Inclusive date range.
    asset:
        GEE asset id (default CHIRPS v2 daily; see module constants for v3).
    gee_project:
        Google Cloud project for ``ee.Initialize``.

    Returns
    -------
    xarray.Dataset
        Daily ``rainfall`` (mm/day), dims (time, lat, lon).

    Raises
    ------
    IngestUnavailable
        If ``earthengine-api`` / auth / network unavailable.
    """
    ee = require("ee", "pip install earthengine-api && earthengine authenticate")
    try:
        ee.Initialize(project=gee_project) if gee_project else ee.Initialize()
    except Exception as exc:
        raise IngestUnavailable(
            f"Earth Engine init failed ({exc}); run `earthengine authenticate`."
        ) from exc

    w, s, e, n = bbox
    region = ee.Geometry.Rectangle([w, s, e, n])
    try:
        coll = (
            ee.ImageCollection(asset)
            .select(GEE_BAND)
            .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
            .filterBounds(region)
        )
        _ = coll.size().getInfo()
    except Exception as exc:
        raise IngestUnavailable(f"CHIRPS GEE query failed ({exc}).") from exc

    return _to_xarray(ee, region, start, end, coll, asset)


def _to_xarray(ee, region, start: date, end: date, coll, asset: str):
    """Materialise daily CHIRPS images into an xarray.Dataset."""
    xr = require("xarray", "pip install xarray")
    np = require("numpy", "pip install numpy")
    pd = require("pandas", "pip install pandas")

    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)

    planes, lats, lons = [], None, None
    for day in days:
        img = (
            coll.filterDate(day.isoformat(), (day + timedelta(days=1)).isoformat())
            .first()
            .clip(region)
        )
        arr = img.getRegion(region, 5566).getInfo()  # ~0.05°
        header = arr[0]
        li, lo_i, v_i = header.index("latitude"), header.index("longitude"), header.index(GEE_BAND)
        rows = arr[1:]
        latset = sorted({r[li] for r in rows})
        lonset = sorted({r[lo_i] for r in rows})
        grid = {(r[li], r[lo_i]): (r[v_i] or 0.0) for r in rows}
        plane = np.array([[grid.get((la, lo), np.nan) for lo in lonset] for la in latset])
        planes.append(plane)
        lats, lons = latset, lonset

    cube = np.stack(planes, axis=0)
    ds = xr.Dataset(
        {"rainfall": (("time", "lat", "lon"), cube)},
        coords={"time": pd.to_datetime([d.isoformat() for d in days]),
                "lat": lats, "lon": lons},
    )
    ds["rainfall"].attrs.update(units="mm/day", source=f"CHIRPS ({asset})")
    ds.attrs.update(source="CHIRPS", crs="EPSG:4326")
    return ds


__all__ = ["fetch", "GEE_V2", "GEE_V3_SAT", "GEE_V3_RNL", "GEE_BAND"]
