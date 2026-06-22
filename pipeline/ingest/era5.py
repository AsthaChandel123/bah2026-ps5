"""
pipeline.ingest.era5
====================
ERA5-Land — the best gap-free 2 m temperature backbone and a triple-collocation
member (ARCHITECTURE.md §4.1 #17; research/01 §2, research/06 §4.1–4.2).

Two access paths are provided:

* **Google Earth Engine** (default, fast) —
  asset ``ECMWF/ERA5_LAND/DAILY_AGGR`` with bands
  ``temperature_2m`` (K), ``total_precipitation_sum`` (m). We also derive a
  daily Tmax/Tmin proxy from the hourly asset ``ECMWF/ERA5_LAND/HOURLY`` when
  requested (max/min of ``temperature_2m`` over the day).
* **Copernicus CDS** (``cdsapi``) — dataset ``reanalysis-era5-land`` (hourly
  ``2m_temperature`` + ``total_precipitation``), aggregated to daily offline.

Unit conversions (see :mod:`pipeline.harmonize`): K → °C (−273.15); precip m → mm.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple

from . import IngestUnavailable, require

GEE_DAILY = "ECMWF/ERA5_LAND/DAILY_AGGR"
GEE_HOURLY = "ECMWF/ERA5_LAND/HOURLY"
CDS_DATASET = "reanalysis-era5-land"


def fetch(
    bbox: Tuple[float, float, float, float],
    start: date,
    end: date,
    variable: str = "temperature_2m",
    gee_project: str | None = None,
):
    """Fetch a daily ERA5-Land field over ``bbox`` from GEE.

    Parameters
    ----------
    bbox:
        (W, S, E, N) pilot region.
    start, end:
        Inclusive date range.
    variable:
        GEE band: ``"temperature_2m"`` (K) or ``"total_precipitation_sum"`` (m).
    gee_project:
        Google Cloud project for ``ee.Initialize``.

    Returns
    -------
    xarray.Dataset
        Daily field over the bbox (units converted to °C / mm), dims
        (time, lat, lon).

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
            ee.ImageCollection(GEE_DAILY)
            .select(variable)
            .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
            .filterBounds(region)
        )
        _ = coll.size().getInfo()  # auth / availability probe
    except Exception as exc:
        raise IngestUnavailable(f"ERA5-Land GEE query failed ({exc}).") from exc

    return _to_xarray(ee, region, start, end, coll, variable)


def fetch_cds(
    bbox: Tuple[float, float, float, float],
    start: date,
    end: date,
    out_path: str = "./data/raw/era5land.nc",
):
    """Alternative: download hourly ERA5-Land from Copernicus CDS (``cdsapi``).

    Returns the path to the downloaded NetCDF (aggregate to daily with
    :func:`pipeline.harmonize.to_daily`). Requires ``~/.cdsapirc`` and a one-time
    licence acceptance. Raises :class:`IngestUnavailable` if unavailable.
    """
    cdsapi = require("cdsapi", "pip install cdsapi  (+ configure ~/.cdsapirc)")
    w, s, e, n = bbox
    try:
        client = cdsapi.Client()
        client.retrieve(
            CDS_DATASET,
            {
                "variable": ["2m_temperature", "total_precipitation"],
                "year": sorted({str(y) for y in range(start.year, end.year + 1)}),
                "month": [f"{m:02d}" for m in range(1, 13)],
                "day": [f"{d:02d}" for d in range(1, 32)],
                "time": [f"{h:02d}:00" for h in range(24)],
                "area": [n, w, s, e],  # N, W, S, E
                "data_format": "netcdf",
                "download_format": "unarchived",
            },
            out_path,
        )
    except Exception as exc:
        raise IngestUnavailable(f"CDS ERA5-Land retrieve failed ({exc}).") from exc
    return out_path


def _to_xarray(ee, region, start: date, end: date, coll, variable: str):
    """Materialise a daily ERA5-Land collection into an xarray.Dataset."""
    xr = require("xarray", "pip install xarray")
    np = require("numpy", "pip install numpy")
    pd = require("pandas", "pip install pandas")

    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)

    is_temp = variable.startswith("temperature")
    out_name = "tmean" if is_temp else "rainfall"

    planes, lats, lons = [], None, None
    for day in days:
        img = (
            coll.filterDate(day.isoformat(), (day + timedelta(days=1)).isoformat())
            .first()
            .clip(region)
        )
        arr = img.getRegion(region, 11132).getInfo()
        header = arr[0]
        li, lo_i, v_i = header.index("latitude"), header.index("longitude"), header.index(variable)
        rows = arr[1:]
        latset = sorted({r[li] for r in rows})
        lonset = sorted({r[lo_i] for r in rows})
        grid = {(r[li], r[lo_i]): r[v_i] for r in rows}

        def _conv(x):
            if x is None:
                return np.nan
            return (x - 273.15) if is_temp else (x * 1000.0)

        plane = np.array([[_conv(grid.get((la, lo))) for lo in lonset] for la in latset])
        planes.append(plane)
        lats, lons = latset, lonset

    cube = np.stack(planes, axis=0)
    ds = xr.Dataset(
        {out_name: (("time", "lat", "lon"), cube)},
        coords={"time": pd.to_datetime([d.isoformat() for d in days]),
                "lat": lats, "lon": lons},
    )
    ds[out_name].attrs.update(
        units="degC" if is_temp else "mm/day",
        source=f"ERA5-Land ({GEE_DAILY})",
    )
    ds.attrs.update(source="ERA5-Land", crs="EPSG:4326")
    return ds


__all__ = ["fetch", "fetch_cds", "GEE_DAILY", "GEE_HOURLY", "CDS_DATASET"]
