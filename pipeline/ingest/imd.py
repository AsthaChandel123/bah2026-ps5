"""
pipeline.ingest.imd
===================
IMD gridded ``_Bin`` ingestion — the MANDATED national ground-truth anchor.

Two readers (research/06 §1):

* **Method A — ``imdlib``** (recommended): downloads the IMD ``.grd`` archive
  and reads it straight into xarray. Variables: ``rain`` (0.25°), ``tmax`` /
  ``tmin`` (1.0°).
* **Method B — direct ``numpy.fromfile``** (robust fallback): parses an already-
  downloaded ``.grd`` Fortran direct-access binary with the exact grid specs
  below, used when ``imdlib``'s scraper breaks.

Exact grid specs (CONFIRMED, research/06 §1.2):

* Rainfall 0.25°  : 135 (lon) × 129 (lat); lon 66.5→100.0°E, lat 6.5→38.5°N;
                    little-endian float32, lon fastest, S→N; nodata −999.0; unit mm.
* Tmax/Tmin 1.0°  : 31 (lon) × 31 (lat); lon 67.5→97.5°E, lat 7.5→37.5°N;
                    nodata 99.9; unit °C.

Source pages: https://imdpune.gov.in/cmpg/Griddata/
imdlib: https://github.com/iamsaswata/imdlib  (paper doi:10.1016/j.envsoft.2023.105869)
"""

from __future__ import annotations

from datetime import date
from typing import Tuple

from . import IngestUnavailable, require

# Confirmed IMD grid definitions (lon0, lat0, nlon, nlat, dres, nodata, unit).
_IMD_GRIDS = {
    "rain": dict(lon0=66.5, lat0=6.5, nlon=135, nlat=129, dres=0.25, nodata=-999.0, unit="mm"),
    "tmax": dict(lon0=67.5, lat0=7.5, nlon=31, nlat=31, dres=1.0, nodata=99.9, unit="degC"),
    "tmin": dict(lon0=67.5, lat0=7.5, nlon=31, nlat=31, dres=1.0, nodata=99.9, unit="degC"),
}


def fetch(
    bbox: Tuple[float, float, float, float],
    start: date,
    end: date,
    var: str = "rain",
    file_dir: str = "./data/raw/imd",
):
    """Fetch IMD gridded data for ``var`` over ``[start, end]`` via ``imdlib``.

    Parameters
    ----------
    bbox:
        (W, S, E, N) used to subset the national grid to the pilot region.
    start, end:
        Inclusive date range. ``imdlib`` works on whole years; we download the
        spanned years then slice.
    var:
        One of ``"rain"`` (0.25°), ``"tmax"``, ``"tmin"`` (1.0°).
    file_dir:
        Where ``imdlib`` caches the ``.grd`` archive (git-ignored ``data/raw``).

    Returns
    -------
    xarray.Dataset
        Daily ``var`` over the pilot bbox, dims (time, lat, lon), EPSG:4326.

    Raises
    ------
    IngestUnavailable
        If ``imdlib``/network is unavailable (orchestrator → synthetic).
    """
    if var not in _IMD_GRIDS:
        raise ValueError(f"IMD var must be one of {list(_IMD_GRIDS)}, got {var!r}")

    imd = require(
        "imdlib",
        "pip install imdlib  (reads IMD .grd; needs network to download archive)",
    )
    try:
        handle = imd.get_data(
            var, start.year, end.year, fn_format="yearwise", file_dir=file_dir
        )
        ds = handle.get_xarray()
    except Exception as exc:  # network / scrape / parse failure
        raise IngestUnavailable(
            f"imdlib could not fetch IMD '{var}' {start.year}-{end.year}: {exc}. "
            f"Fallback: download .grd manually and use read_grd()."
        ) from exc

    ds = _subset_bbox(ds, bbox)
    ds = ds.sel(time=slice(start.isoformat(), end.isoformat()))
    ds.attrs.update(source="IMD gridded (imdlib)", variable=var, crs="EPSG:4326")
    return ds


def read_grd(path: str, year: int, var: str = "rain"):
    """Method B: parse an IMD ``.grd`` directly with ``numpy.fromfile``.

    Mirrors the Fortran direct-access layout (research/06 §1.4): a header-less
    stream of ``ndays × nlat × nlon`` little-endian float32, longitude fastest,
    latitude South→North. Robust to leap-year off-by-one (trims to file size).

    Returns an ``xarray.DataArray`` (time, lat, lon). Raises
    :class:`IngestUnavailable` if numpy/xarray are missing.
    """
    np = require("numpy", "pip install numpy")
    xr = require("xarray", "pip install xarray")
    pd = require("pandas", "pip install pandas")

    g = _IMD_GRIDS[var]
    nlon, nlat = g["nlon"], g["nlat"]
    lon = np.linspace(g["lon0"], g["lon0"] + (nlon - 1) * g["dres"], nlon)
    lat = np.linspace(g["lat0"], g["lat0"] + (nlat - 1) * g["dres"], nlat)

    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    ndays = 366 if leap else 365

    raw = np.fromfile(path, dtype="<f4")  # little-endian float32, no header
    expected = ndays * nlat * nlon
    if raw.size != expected:  # trim/pad off-by-leap years
        ndays = raw.size // (nlat * nlon)
        raw = raw[: ndays * nlat * nlon]

    arr = raw.reshape(ndays, nlat, nlon)
    arr = np.where(arr == g["nodata"], np.nan, arr)

    time = pd.date_range(f"{year}-01-01", periods=ndays, freq="D")
    da = xr.DataArray(
        arr,
        dims=("time", "lat", "lon"),
        coords={"time": time, "lat": lat, "lon": lon},
        name=var,
        attrs={"units": g["unit"], "source": "IMD gridded (.grd direct read)"},
    )
    return da


def _subset_bbox(ds, bbox: Tuple[float, float, float, float]):
    """Slice a dataset to (W, S, E, N), handling ascending/descending lat."""
    w, s, e, n = bbox
    lat = ds["lat"]
    if float(lat[0]) <= float(lat[-1]):
        ds = ds.sel(lat=slice(s, n), lon=slice(w, e))
    else:  # descending latitude
        ds = ds.sel(lat=slice(n, s), lon=slice(w, e))
    return ds


__all__ = ["fetch", "read_grd"]
