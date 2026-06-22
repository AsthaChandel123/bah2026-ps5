"""
pipeline.ingest.modis_lst
=========================
MODIS Land Surface Temperature — fine (1 km) LST truth used to bias-correct the
coarse INSAT LST and as a temperature triple-collocation member
(ARCHITECTURE.md §4.1 #22; research/01 §4, research/06 §4.1).

Access via Google Earth Engine:
    Terra : ``MODIS/061/MOD11A1``  band ``LST_Day_1km``
    Aqua  : ``MODIS/061/MYD11A1``  band ``LST_Day_1km``
Scaling: LST DN × 0.02 − 273.15 → °C (the band is in 0.02 K).

A NASA Earthdata (``earthaccess``) path exists via short_name ``MOD11A1`` /
``MYD11A1``; the GEE path is the fastest for a small pilot box.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple

from . import IngestUnavailable, require

GEE_TERRA = "MODIS/061/MOD11A1"
GEE_AQUA = "MODIS/061/MYD11A1"
GEE_BAND = "LST_Day_1km"


def fetch(
    bbox: Tuple[float, float, float, float],
    start: date,
    end: date,
    platform: str = "terra",
    gee_project: str | None = None,
):
    """Fetch daily MODIS LST (°C) over ``bbox`` from GEE.

    Parameters
    ----------
    bbox:
        (W, S, E, N) pilot region.
    start, end:
        Inclusive date range.
    platform:
        ``"terra"`` (MOD11A1) or ``"aqua"`` (MYD11A1).
    gee_project:
        Google Cloud project for ``ee.Initialize``.

    Returns
    -------
    xarray.Dataset
        Daily ``lst`` (°C) over the bbox, dims (time, lat, lon).

    Raises
    ------
    IngestUnavailable
        If ``earthengine-api`` / auth / network unavailable.
    """
    asset = GEE_AQUA if platform.lower() == "aqua" else GEE_TERRA
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
        raise IngestUnavailable(f"MODIS LST GEE query failed ({exc}).") from exc

    return _to_xarray(ee, region, start, end, coll, asset)


def _to_xarray(ee, region, start: date, end: date, coll, asset: str):
    """Materialise daily MODIS LST images into an xarray.Dataset (°C)."""
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
        )
        if img is None:
            continue
        img = img.clip(region)
        arr = img.getRegion(region, 1000).getInfo()
        header = arr[0]
        li, lo_i, v_i = header.index("latitude"), header.index("longitude"), header.index(GEE_BAND)
        rows = arr[1:]
        latset = sorted({r[li] for r in rows})
        lonset = sorted({r[lo_i] for r in rows})
        grid = {(r[li], r[lo_i]): r[v_i] for r in rows}
        # DN × 0.02 − 273.15 → °C.
        plane = np.array(
            [[(grid.get((la, lo)) * 0.02 - 273.15) if grid.get((la, lo)) else np.nan
              for lo in lonset] for la in latset]
        )
        planes.append(plane)
        lats, lons = latset, lonset

    cube = np.stack(planes, axis=0)
    ds = xr.Dataset(
        {"lst": (("time", "lat", "lon"), cube)},
        coords={"time": pd.to_datetime([d.isoformat() for d in days]),
                "lat": lats, "lon": lons},
    )
    ds["lst"].attrs.update(units="degC", source=f"MODIS LST ({asset})")
    ds.attrs.update(source="MODIS LST", crs="EPSG:4326")
    return ds


__all__ = ["fetch", "GEE_TERRA", "GEE_AQUA", "GEE_BAND"]
