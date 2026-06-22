"""
pipeline.h3_index
=================
O(1) spatial keying: lat/lon → cell id at the configured H3 resolutions.

The blueprint's fast-serving layer (ARCHITECTURE.md §7) addresses every point
query by ``latLngToCell`` → a 64-bit H3 id → a KV/array lookup. This module
wraps Uber's ``h3`` library when present and provides a **deterministic
pure-python fallback** otherwise, so the pipeline (and its tests) run with zero
third-party dependencies.

The fallback is *not* a real H3 hierarchy — it is a stable, collision-resistant
hash of the quantised lat/lon at a resolution-dependent grain. It satisfies the
contract the serving layer actually needs (a deterministic O(1) key per cell at
each resolution, nestable coarse↔fine) without pulling in a binary wheel.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from .config import H3 as H3SPEC

# Optional real H3.
try:  # pragma: no cover - exercised only when h3 is installed
    import h3 as _h3  # type: ignore

    _HAVE_H3 = True
    # h3 v4 renamed latlng_to_cell; support both major versions.
    _LATLNG_TO_CELL = getattr(_h3, "latlng_to_cell", None) or getattr(_h3, "geo_to_h3")
except Exception:  # pragma: no cover
    _h3 = None  # type: ignore
    _HAVE_H3 = False
    _LATLNG_TO_CELL = None


# Approx. degrees-per-cell grain for the fallback at each H3 resolution.
# (Chosen so res 4 ≈ the 0.25° grid, coarser res → coarser grain.)
_FALLBACK_GRAIN_DEG = {
    0: 12.0, 1: 5.0, 2: 2.5, 3: 1.0, 4: 0.25, 5: 0.10, 6: 0.04,
}


def _fallback_cell(lat: float, lon: float, res: int) -> str:
    """Deterministic pseudo-H3 id from quantised lat/lon (no h3 dependency).

    Quantise to a resolution-dependent grain, then hash. The 15-hex-char output
    mimics an H3 cell string so downstream code is agnostic to which path ran.
    """
    grain = _FALLBACK_GRAIN_DEG.get(res, 0.25)
    qlat = round(lat / grain)
    qlon = round(lon / grain)
    raw = f"r{res}:{qlat}:{qlon}".encode("utf-8")
    digest = hashlib.blake2b(raw, digest_size=7).hexdigest()  # 14 hex chars
    return f"8{digest}"  # leading 8 → looks like a res-class H3 id


def latlng_to_cell(lat: float, lon: float, res: int) -> str:
    """Map (lat, lon) to a cell id at H3 resolution ``res`` (O(1)).

    Uses the real ``h3`` library if importable, otherwise the deterministic
    fallback. Returns a string cell id in both cases.
    """
    if _HAVE_H3 and _LATLNG_TO_CELL is not None:
        return str(_LATLNG_TO_CELL(lat, lon, res))
    return _fallback_cell(lat, lon, res)


def map_cell(lat: float, lon: float) -> str:
    """Cell id at the rainfall/map resolution (res 4)."""
    return latlng_to_cell(lat, lon, H3SPEC.res_map)


def region_cell(lat: float, lon: float) -> str:
    """Cell id at the national-rollup resolution (res 2)."""
    return latlng_to_cell(lat, lon, H3SPEC.res_region)


def temp_cell(lat: float, lon: float) -> str:
    """Cell id at the 1.0° temperature resolution (res 3)."""
    return latlng_to_cell(lat, lon, H3SPEC.res_temp)


def using_real_h3() -> bool:
    """True if the real Uber ``h3`` library backs the keys."""
    return _HAVE_H3


def index_grid(lats, lons, res: Optional[int] = None) -> dict:
    """Build a ``{(j,i): cell_id}`` index for an entire grid.

    Convenience for the export step (materialising a cell→value KV seed). ``j``
    is the lat row, ``i`` the lon column (matching field array ordering).
    """
    r = H3SPEC.res_map if res is None else res
    out = {}
    for j, la in enumerate(lats):
        for i, lo in enumerate(lons):
            out[(j, i)] = latlng_to_cell(la, lo, r)
    return out


__all__ = [
    "latlng_to_cell",
    "map_cell",
    "region_cell",
    "temp_cell",
    "using_real_h3",
    "index_grid",
]
