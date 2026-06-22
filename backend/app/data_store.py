"""In-memory O(1) data store for the Bharat Climate Twin serving API.

The pilot grid is tiny (Marathwada: 14 lat x 20 lon x 365 days), so every
precomputed artifact in ``data/processed/sample/`` fits comfortably in RAM. We
load them **once** at process startup and answer every request with direct
index / dict lookups — no per-request file I/O, no scans.

O(1) addressing
---------------
The analysis grid is a *regular* 0.25 deg lat/lon grid. A geographic point is
mapped to a cell with closed-form arithmetic (no search)::

    i = round((lat - lat0) / res)        # latitude index  (S -> N)
    j = round((lon - lon0) / res)        # longitude index (W -> E)

where ``(lat0, lon0)`` is the south-west cell centre and ``res`` the grid
spacing. That is O(1). We additionally build an **H3-keyed dict**
``{h3_cell_id -> (i, j)}`` so a point can also be addressed by its Uber H3
res-4 index exactly as ARCHITECTURE.md S7 describes. If the optional ``h3``
library is unavailable we fall back to a pure-python integer cell hash that is
still a deterministic O(1) address (it just is not a real H3 index).

Everything in this module is plain stdlib + optional numpy/h3 (guarded
imports), so the service runs with only ``fastapi``/``uvicorn`` installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Optional acceleration / indexing libraries (guarded — never required).
# --------------------------------------------------------------------------- #
try:  # numpy makes the what-if recompute and aggregations faster, but is optional.
    import numpy as _np  # type: ignore

    HAVE_NUMPY = True
except Exception:  # pragma: no cover - environment without numpy
    _np = None  # type: ignore
    HAVE_NUMPY = False

try:  # h3 gives real Uber H3 cell ids; we degrade to a synthetic hash otherwise.
    import h3 as _h3  # type: ignore

    HAVE_H3 = True
except Exception:  # pragma: no cover - environment without h3
    _h3 = None  # type: ignore
    HAVE_H3 = False


# Canonical artifact filenames (must mirror CONTRACT.md / frontend exactly).
ARTIFACT_FILES: Dict[str, str] = {
    "metadata": "metadata.json",
    "fields_daily": "fields_daily.json",
    "climatology": "climatology.json",
    "uncertainty": "uncertainty.json",
    "scenarios": "scenarios.json",
    "sources": "sources.json",
    "metrics": "metrics.json",
    # forecast.json is optional — served only if present.
    "forecast": "forecast.json",
}

# Variables that have real daily fields (uncertainty is a derived static layer).
BASE_VARS: Tuple[str, ...] = ("rainfall", "tmax", "tmin")


def _default_data_dir() -> Path:
    """Locate ``data/processed/sample`` relative to the repo, override via env."""
    import os

    env = os.environ.get("BCT_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # backend/app/data_store.py -> repo root is three parents up.
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "data" / "processed" / "sample"


@dataclass
class DataStore:
    """Constant-time, in-memory store of all precomputed serving artifacts.

    Attributes are populated by :meth:`load`. After loading, every public
    accessor performs only arithmetic and dict / list indexing (O(1) in the
    size of the dataset).
    """

    data_dir: Path = field(default_factory=_default_data_dir)

    # Raw artifacts (parsed JSON), keyed by logical name.
    artifacts: Dict[str, Any] = field(default_factory=dict)

    # Grid geometry (cached from metadata for O(1) index math).
    lats: List[float] = field(default_factory=list)
    lons: List[float] = field(default_factory=list)
    dates: List[str] = field(default_factory=list)
    res: float = 0.25
    lat0: float = 0.0
    lon0: float = 0.0
    nlat: int = 0
    nlon: int = 0
    ntime: int = 0

    # Fast lookup tables built once at startup.
    _date_index: Dict[str, int] = field(default_factory=dict)
    _h3_to_ij: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    _ij_to_h3: Dict[Tuple[int, int], str] = field(default_factory=dict)
    h3_res: int = 4

    # numpy views of the field cube (built only if numpy present); used to
    # accelerate the what-if recompute. Shape (ntime, nlat, nlon).
    _np_fields: Dict[str, Any] = field(default_factory=dict)
    # Per-cell heavy-rain (p90 of wet days) threshold grid, computed once.
    _p90_grid: Optional[List[List[float]]] = None
    _p90_percentile: float = 90.0

    loaded: bool = False

    # ----------------------------------------------------------------- load #
    def load(self) -> "DataStore":
        """Read every artifact from disk **once** and build lookup tables.

        Missing optional artifacts (e.g. ``forecast.json``) are skipped without
        error. Raises ``FileNotFoundError`` only for the mandatory metadata /
        fields artifacts that the whole service depends on.
        """
        for name, fname in ARTIFACT_FILES.items():
            path = self.data_dir / fname
            if path.exists():
                with path.open("r", encoding="utf-8") as fh:
                    self.artifacts[name] = json.load(fh)
            elif name in ("metadata", "fields_daily"):
                raise FileNotFoundError(
                    f"Required artifact '{fname}' not found in {self.data_dir}. "
                    "Set BCT_DATA_DIR to the directory containing the "
                    "precomputed JSON artifacts."
                )
            # else: optional artifact absent -> leave unset.

        self._build_grid()
        self._build_h3_index()
        self._build_numpy_cube()
        self.loaded = True
        return self

    def _build_grid(self) -> None:
        """Cache grid geometry from metadata for O(1) index arithmetic."""
        meta = self.artifacts["metadata"]
        grid = meta["grid"]
        self.lats = [float(x) for x in grid["lats"]]
        self.lons = [float(x) for x in grid["lons"]]
        self.res = float(grid.get("res_deg", 0.25))
        self.nlat = int(grid.get("nlat", len(self.lats)))
        self.nlon = int(grid.get("nlon", len(self.lons)))
        self.lat0 = self.lats[0]
        self.lon0 = self.lons[0]

        self.dates = list(meta["time"]["dates"])
        self.ntime = int(meta["time"].get("n", len(self.dates)))
        # date -> index map for O(1) date resolution.
        self._date_index = {d: k for k, d in enumerate(self.dates)}
        # H3 resolution for the map layer (res-4 for 0.25 deg per ARCHITECTURE).
        self.h3_res = int(meta.get("h3", {}).get("res_map", 4))

    def _build_h3_index(self) -> None:
        """Build ``{cell_id -> (i, j)}`` and inverse, one entry per grid cell.

        With the real ``h3`` library the key is a true Uber H3 res-4 index; the
        dashboard click handler can therefore hand us an H3 id and we resolve it
        in O(1). Without ``h3`` we synthesise a deterministic string id so the
        same code path works (it is still an O(1) hash, just not a real cell).
        """
        self._h3_to_ij.clear()
        self._ij_to_h3.clear()
        for i, lat in enumerate(self.lats):
            for j, lon in enumerate(self.lons):
                cid = self._cell_id(lat, lon)
                self._h3_to_ij[cid] = (i, j)
                self._ij_to_h3[(i, j)] = cid

    def _cell_id(self, lat: float, lon: float) -> str:
        """Return an H3 cell id (or synthetic fallback) for a lat/lon."""
        if HAVE_H3:
            # h3 v4 API: latlng_to_cell; v3 fallback: geo_to_h3.
            if hasattr(_h3, "latlng_to_cell"):
                return _h3.latlng_to_cell(lat, lon, self.h3_res)  # type: ignore[attr-defined]
            return _h3.geo_to_h3(lat, lon, self.h3_res)  # type: ignore[attr-defined]
        # Deterministic synthetic id: encode the integer grid address.
        i = self._lat_to_i(lat)
        j = self._lon_to_j(lon)
        return f"cell-r{self.h3_res}-{i:03d}-{j:03d}"

    def _build_numpy_cube(self) -> None:
        """Optionally mirror the field cube as numpy arrays for fast what-if."""
        if not HAVE_NUMPY:
            return
        fields = self.artifacts.get("fields_daily")
        if not fields:
            return
        for var in BASE_VARS:
            if var in fields:
                self._np_fields[var] = _np.asarray(fields[var], dtype="float64")

    # ----------------------------------------------------- index arithmetic #
    def _lat_to_i(self, lat: float) -> int:
        """Closed-form O(1) latitude index, clamped to the grid."""
        i = round((lat - self.lat0) / self.res)
        return max(0, min(self.nlat - 1, int(i)))

    def _lon_to_j(self, lon: float) -> int:
        """Closed-form O(1) longitude index, clamped to the grid."""
        j = round((lon - self.lon0) / self.res)
        return max(0, min(self.nlon - 1, int(j)))

    def nearest_cell(self, lat: float, lon: float) -> Tuple[int, int]:
        """Map a geographic point to its nearest grid-cell ``(i, j)`` in O(1)."""
        return self._lat_to_i(lat), self._lon_to_j(lon)

    def cell_id(self, i: int, j: int) -> str:
        """Return the (H3 or synthetic) cell id for grid indices ``(i, j)``."""
        return self._ij_to_h3.get((i, j), self._cell_id(self.lats[i], self.lons[j]))

    def ij_from_cell_id(self, cell_id: str) -> Optional[Tuple[int, int]]:
        """Resolve a cell id back to ``(i, j)`` via the prebuilt dict (O(1))."""
        return self._h3_to_ij.get(cell_id)

    def date_to_index(self, date: str) -> Optional[int]:
        """O(1) date -> time index lookup; ``None`` if the date is unknown."""
        return self._date_index.get(date)

    def resolve_time_index(self, date: Optional[str]) -> int:
        """Resolve a date string (or ``None`` -> last day) to a time index.

        Raises ``KeyError`` if a non-empty date is not on the time axis.
        """
        if date is None or date == "":
            return self.ntime - 1
        idx = self._date_index.get(date)
        if idx is None:
            raise KeyError(date)
        return idx

    # --------------------------------------------------------- accessors #
    def get_artifact(self, name: str) -> Optional[Any]:
        """Return a raw artifact by logical name (O(1) dict lookup)."""
        return self.artifacts.get(name)

    def field_slice(self, var: str, time_index: int) -> List[List[float]]:
        """Return the ``[lat][lon]`` grid for one variable & timestep (O(1))."""
        fields = self.artifacts["fields_daily"]
        return fields[var][time_index]

    def cell_series(self, var: str, i: int, j: int) -> List[float]:
        """Return a single cell's full daily series for ``var`` (O(ntime))."""
        fields = self.artifacts["fields_daily"]
        col = fields[var]
        return [col[t][i][j] for t in range(self.ntime)]

    def cell_uncertainty(self, var: str, i: int, j: int) -> Optional[float]:
        """Return the static per-cell uncertainty value for ``var`` (O(1))."""
        unc = self.artifacts.get("uncertainty")
        if not unc or var not in unc:
            return None
        try:
            return unc[var][i][j]
        except (IndexError, KeyError, TypeError):
            return None

    def numpy_field(self, var: str):
        """Return the numpy view of a field cube (or ``None`` if unavailable)."""
        return self._np_fields.get(var)

    # ------------------------------------------------- heavy-rain threshold #
    def heavy_rain_threshold_grid(self, percentile: float = 90.0) -> List[List[float]]:
        """Per-cell p-percentile of **wet** (>0) rainfall days, computed once.

        This mirrors ``frontend/lib/whatif.ts::heavyRainThresholdGrid`` exactly:
        for each cell, collect days with rainfall > 0, sort ascending, and take
        the value at ``floor(percentile/100 * (len-1))`` (clamped). Cells with no
        wet days get ``+inf`` (never "heavy"). Cached so it is built only once.
        """
        if self._p90_grid is not None and self._p90_percentile == percentile:
            return self._p90_grid

        fields = self.artifacts["fields_daily"]
        rain = fields["rainfall"]
        grid: List[List[float]] = []
        for i in range(self.nlat):
            row: List[float] = []
            for j in range(self.nlon):
                series = [rain[t][i][j] for t in range(self.ntime) if rain[t][i][j] > 0]
                if not series:
                    row.append(float("inf"))
                    continue
                series.sort()
                idx = int((percentile / 100.0) * (len(series) - 1))
                idx = max(0, min(len(series) - 1, idx))
                row.append(series[idx])
            grid.append(row)
        self._p90_grid = grid
        self._p90_percentile = percentile
        return grid

    def heavy_rain_percentile(self) -> float:
        """Heavy-rain percentile from scenarios.physics (default 90)."""
        scen = self.artifacts.get("scenarios") or {}
        phys = scen.get("physics", {})
        return float(phys.get("heavy_rain_percentile", 90.0))

    def cc_pct_per_degc(self) -> float:
        """Clausius-Clapeyron %/degC from scenarios.physics (default 7)."""
        scen = self.artifacts.get("scenarios") or {}
        phys = scen.get("physics", {})
        return float(phys.get("clausius_clapeyron_pct_per_degC", 7.0))

    # --------------------------------------------------------------- meta #
    def summary(self) -> Dict[str, Any]:
        """Lightweight health/diagnostics summary (no large payloads)."""
        return {
            "loaded": self.loaded,
            "data_dir": str(self.data_dir),
            "artifacts": sorted(self.artifacts.keys()),
            "grid": {
                "res_deg": self.res,
                "nlat": self.nlat,
                "nlon": self.nlon,
                "ntime": self.ntime,
            },
            "cells": self.nlat * self.nlon,
            "h3": {
                "enabled": HAVE_H3,
                "res": self.h3_res,
                "indexed_cells": len(self._h3_to_ij),
            },
            "numpy": HAVE_NUMPY,
        }


# Module-level singleton populated by the FastAPI lifespan handler.
STORE = DataStore()


def get_store() -> DataStore:
    """FastAPI dependency: return the loaded module-level store."""
    return STORE
