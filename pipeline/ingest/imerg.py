"""
pipeline.ingest.imerg
=====================
GPM IMERG V07 — the primary satellite rainfall source and a triple-collocation
member (ARCHITECTURE.md §4.1 #10; research/01 §3, research/06 §4.1).

Access via Google Earth Engine:
    asset  : ``NASA/GPM_L3/IMERG_V07``
    band   : ``precipitation``  (units mm/hr, 30-min cadence, 0.1°)
Conversion to mm/day: each 30-min slot is mm/hr × 0.5 h; sum the slots in a day.

A NASA Earthdata (``earthaccess``) path is noted in the docstring as the
alternative (short_name ``GPM_3IMERGDF`` for the daily product).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple

from . import IngestUnavailable, require

GEE_ASSET = "NASA/GPM_L3/IMERG_V07"
GEE_BAND = "precipitation"
EARTHDATA_SHORT_NAME = "GPM_3IMERGDF"  # IMERG Final daily V07


def fetch(
    bbox: Tuple[float, float, float, float],
    start: date,
    end: date,
    gee_project: str | None = None,
):
    """Fetch daily IMERG rainfall (mm/day) over ``bbox`` from GEE.

    Parameters
    ----------
    bbox:
        (W, S, E, N) pilot region.
    start, end:
        Inclusive date range.
    gee_project:
        Google Cloud project for ``ee.Initialize`` (or rely on a prior auth).

    Returns
    -------
    xarray.Dataset
        Daily ``rainfall`` (mm/day) over the bbox, dims (time, lat, lon).

    Raises
    ------
    IngestUnavailable
        If ``earthengine-api`` / auth / network unavailable.
    """
    # The PyPI package is `earthengine-api` but the import name is `ee`.
    ee = require("ee", "pip install earthengine-api && earthengine authenticate")

    try:
        ee.Initialize(project=gee_project) if gee_project else ee.Initialize()
    except Exception as exc:
        raise IngestUnavailable(
            f"Earth Engine init failed ({exc}). Run `earthengine authenticate` "
            f"and pass gee_project=YOUR_GCP_PROJECT."
        ) from exc

    w, s, e, n = bbox
    region = ee.Geometry.Rectangle([w, s, e, n])

    def _daily_sum(day_start: date):
        d0 = day_start.isoformat()
        d1 = (day_start + timedelta(days=1)).isoformat()
        half_hourly = (
            ee.ImageCollection(GEE_ASSET)
            .select(GEE_BAND)
            .filterDate(d0, d1)
            .filterBounds(region)
        )
        # mm/hr × 0.5 h per 30-min slot, summed over the day → mm/day.
        return half_hourly.sum().multiply(0.5).clip(region).set("date", d0)

    # NOTE: pulling pixel arrays out of EE requires getInfo()/Export; we leave the
    # heavy materialisation to the live precompute job and surface the collection
    # builder here so the orchestrator can detect availability deterministically.
    try:
        sample = _daily_sum(start)
        _ = sample.bandNames().getInfo()  # forces a server round-trip / auth check
    except Exception as exc:
        raise IngestUnavailable(
            f"IMERG GEE query failed ({exc})."
        ) from exc

    # Build an xarray cube from per-day reduced images via getRegion (small bbox).
    return _to_xarray(ee, region, start, end, _daily_sum)


def _to_xarray(ee, region, start: date, end: date, daily_fn):
    """Materialise daily IMERG images into an xarray.Dataset over the bbox."""
    xr = require("xarray", "pip install xarray")
    np = require("numpy", "pip install numpy")
    pd = require("pandas", "pip install pandas")

    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)

    planes = []
    lats = lons = None
    for day in days:
        img = daily_fn(day)
        # getRegion returns [header, *rows]; scale 11132 m ≈ 0.1°.
        arr = img.getRegion(region, 11132).getInfo()
        header = arr[0]
        li, lo_i, val_i = header.index("latitude"), header.index("longitude"), header.index(GEE_BAND)
        rows = arr[1:]
        latset = sorted({r[li] for r in rows})
        lonset = sorted({r[lo_i] for r in rows})
        grid = {(r[li], r[lo_i]): (r[val_i] or 0.0) for r in rows}
        plane = np.array([[grid.get((la, lo), np.nan) for lo in lonset] for la in latset])
        planes.append(plane)
        lats, lons = latset, lonset

    cube = np.stack(planes, axis=0)
    ds = xr.Dataset(
        {"rainfall": (("time", "lat", "lon"), cube)},
        coords={"time": pd.to_datetime([d.isoformat() for d in days]),
                "lat": lats, "lon": lons},
    )
    ds["rainfall"].attrs.update(units="mm/day", source=f"GPM IMERG V07 ({GEE_ASSET})")
    ds.attrs.update(source="GPM IMERG V07", crs="EPSG:4326")
    return ds


__all__ = ["fetch", "GEE_ASSET", "GEE_BAND", "EARTHDATA_SHORT_NAME"]
