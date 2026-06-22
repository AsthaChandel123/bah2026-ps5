"""
pipeline.harmonize
===================
Regrid / align heterogeneous sources to the common 0.25° analysis grid and
unify calendar, units and nodata (ARCHITECTURE.md §4.2). This is the
prerequisite to fusion — it produces the "Generic State Vector" (one format,
one grid, one calendar, one unit system) that the fusion stage consumes.

These functions use **real xarray / numpy** and are intended for the live
ingestion path. They import lazily inside each function so this module is safe
to import even when xarray is absent (the offline-demo path never needs to
regrid — the synthetic generator emits data already on the target grid).

Decisions implemented (ARCHITECTURE.md §4.2 table):

* CRS       : EPSG:4326 everywhere.
* Grid      : regrid all sources to the IMD 0.25° target grid. Conservative
              remap for fluxes (rainfall), bilinear for state (temperature).
              We use ``xarray.interp`` (bilinear/nearest) as the dependency-light
              default and note ``xESMF`` for conservative remap at scale.
* Calendar  : daily UTC; sub-daily aggregated (rain = sum, Tmax = max, Tmin = min).
* Units     : rainfall → mm/day (IMERG mm/hr×0.5 per 30-min slot then sum;
              ERA5 m → mm); temperature → °C (K − 273.15; MODIS LST ×0.02 − 273.15).
* No-data   : mask IMD rain −999.0, temp 99.9; satellite ``_FillValue``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .config import GRID, GridSpec

if TYPE_CHECKING:  # pragma: no cover - typing only
    import xarray as xr


def _require_xarray():
    """Import xarray/numpy or raise a clear error (live path only)."""
    try:
        import numpy as np  # noqa: F401
        import xarray as xr

        return xr, np
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "harmonize requires xarray + numpy (pip install xarray numpy). "
            "The offline-demo path does not call harmonize; synthetic data is "
            "already on the target grid."
        ) from exc


def target_grid_coords(grid: GridSpec = GRID):
    """Return ``(lats, lons)`` numpy arrays for the common target grid."""
    _, np = _require_xarray()
    return np.array(grid.lats, dtype="float64"), np.array(grid.lons, dtype="float64")


def regrid_to_common(
    ds: "xr.Dataset",
    grid: GridSpec = GRID,
    method: str = "bilinear",
    lat_name: str = "lat",
    lon_name: str = "lon",
) -> "xr.Dataset":
    """Regrid a dataset to the common 0.25° grid via ``xarray.interp``.

    Parameters
    ----------
    ds:
        Input dataset with latitude/longitude coordinates.
    grid:
        Target :class:`~pipeline.config.GridSpec`.
    method:
        ``"bilinear"`` for state variables (temperature), ``"conservative"`` for
        fluxes (rainfall). Conservative remap requires ``xESMF``; if unavailable
        we fall back to ``"linear"`` interpolation with a warning in the attrs.
    lat_name, lon_name:
        Names of the spatial coordinates on ``ds``.
    """
    xr, np = _require_xarray()
    tgt_lat, tgt_lon = target_grid_coords(grid)

    if method == "conservative":
        try:  # prefer xESMF conservative remap for fluxes
            import xesmf as xe  # type: ignore

            target = xr.Dataset(
                {"lat": ("lat", tgt_lat), "lon": ("lon", tgt_lon)}
            )
            regridder = xe.Regridder(ds, target, "conservative")
            out = regridder(ds)
            out.attrs["regrid_method"] = "xesmf-conservative"
            return out
        except Exception:
            method = "linear"  # graceful fallback

    out = ds.interp({lat_name: tgt_lat, lon_name: tgt_lon}, method=method)
    out.attrs["regrid_method"] = f"xarray.interp-{method}"
    out.attrs["crs"] = "EPSG:4326"
    return out


def to_daily(ds: "xr.Dataset", how: dict, time_name: str = "time") -> "xr.Dataset":
    """Aggregate a sub-daily dataset to daily with per-variable reducers.

    ``how`` maps variable → reducer, e.g. ``{"rainfall": "sum", "tmax": "max",
    "tmin": "min"}`` (ARCHITECTURE.md §4.2). Variables not in ``how`` use mean.
    """
    xr, _ = _require_xarray()
    grouped = ds.resample({time_name: "1D"})
    pieces = {}
    for var in ds.data_vars:
        reducer = how.get(str(var), "mean")
        pieces[var] = getattr(grouped[var], reducer)()
    return xr.Dataset(pieces)


def normalize_units(da: "xr.DataArray", kind: str) -> "xr.DataArray":
    """Convert a DataArray to the twin's canonical units.

    ``kind`` ∈ {"rain_mm_per_hr","rain_m","temp_K","modis_lst"}:
      * ``rain_mm_per_hr`` IMERG mm/hr → mm/day handled by daily-sum upstream;
        here we just tag units (caller multiplies by slot length if needed).
      * ``rain_m``        ERA5 total precip metres → mm  (×1000).
      * ``temp_K``        kelvin → °C  (−273.15).
      * ``modis_lst``     MODIS LST DN → °C  (×0.02 − 273.15).
    """
    if kind == "rain_m":
        out = da * 1000.0
        out.attrs["units"] = "mm/day"
    elif kind == "temp_K":
        out = da - 273.15
        out.attrs["units"] = "degC"
    elif kind == "modis_lst":
        out = da * 0.02 - 273.15
        out.attrs["units"] = "degC"
    else:  # rain_mm_per_hr or already-correct
        out = da
        out.attrs.setdefault("units", "mm/day")
    return out


def mask_nodata(da: "xr.DataArray", fill_values=(-999.0, 99.9)) -> "xr.DataArray":
    """Replace IMD/satellite nodata sentinels with NaN (ARCHITECTURE.md §4.2)."""
    _, np = _require_xarray()
    out = da
    for fv in fill_values:
        out = out.where(out != fv)
    # also honour an explicit _FillValue attribute if present
    fv_attr = da.attrs.get("_FillValue")
    if fv_attr is not None:
        out = out.where(out != fv_attr)
    return out


__all__ = [
    "target_grid_coords",
    "regrid_to_common",
    "to_daily",
    "normalize_units",
    "mask_nodata",
]
