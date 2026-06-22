"""
pipeline.synthetic
===================
Physically-plausible synthetic climate generator for the Marathwada pilot.

Why this exists
---------------
The stage demo must run with **zero network and zero credentials** (Risk #8 in
ARCHITECTURE.md §16). When real ingestion is unavailable, this module produces
daily ``rainfall`` (mm/day), ``tmax`` and ``tmin`` (°C) over the common 0.25°
grid that *look believable on a map and in seasonal charts* — strong enough to
showcase the twin without claiming to be observations.

It runs on the **Python standard library alone** (``math``/``random``), and
transparently uses ``numpy`` for speed if present. Output is a small
``Grid``-shaped nested-list cube so downstream export needs no array library.

Physics encoded (research/01, ARCHITECTURE.md §3.1)
---------------------------------------------------
* **SW-monsoon seasonality** — JJAS (Jun–Sep) rainfall peak, near-dry winter,
  modelled with a smooth seasonal envelope whose onset can be shifted.
* **West→east spatial gradient** — the Western Ghats / west edge is wetter; the
  interior Marathwada rain-shadow (east) is markedly drier.
* **Temperature structure** — latitude + a mild elevation proxy (the western
  Ghats crest is cooler), a clear **Apr–May pre-monsoon heat peak**, monsoon
  cooling, and a realistic diurnal range (Tmax−Tmin) that *shrinks* in the
  humid monsoon and *widens* in the dry season.
* **Rain↔temperature anti-correlation in the monsoon** — wet days suppress Tmax
  (cloud + evaporative cooling) and lift Tmin (humidity), so the fields move
  oppositely during JJAS, as observed.
* **Wet/dry spells** — rainfall *occurrence* follows a two-state Markov chain
  (persistent wet and dry spells), and wet-day *intensity* is drawn from a
  Gamma distribution (the standard daily-rainfall model).
* **Interannual ENSO-like variability** — a per-year monsoon-strength multiplier
  (El Niño → weaker, La Niña → stronger) drives realistic year-to-year spread.

Determinism
-----------
Everything is seeded (``SEED`` + year), so the artifacts are reproducible.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from .config import GRID, TIME, GridSpec

# Optional acceleration — never required.
try:  # pragma: no cover - exercised only when numpy is installed
    import numpy as _np  # type: ignore

    _HAVE_NUMPY = True
except Exception:  # pragma: no cover
    _np = None  # type: ignore
    _HAVE_NUMPY = False


SEED: int = 20260621  # ISRO BAH 2026 demo seed (stable artifacts)

# Type alias: a daily cube as nested python lists  [ntime][nlat][nlon].
Cube = List[List[List[float]]]


# ──────────────────────────────────────────────────────────────────────────
# ENSO-like interannual monsoon strength
# ──────────────────────────────────────────────────────────────────────────
# Per-year all-India-monsoon-style multiplier (1.0 = normal). Values loosely
# echo real monsoon seasons: 2015 strong El Niño (deficit), 2016/2022 La Niña
# (surplus), 2009 deep deficit. Used to scale JJAS rainfall and nudge heat.
_ENSO_MONSOON_FACTOR: Dict[int, float] = {
    2009: 0.78, 2010: 1.06, 2011: 1.03, 2012: 0.93, 2013: 1.10,
    2014: 0.88, 2015: 0.76, 2016: 1.12, 2017: 0.97, 2018: 0.91,
    2019: 1.09, 2020: 1.07, 2021: 1.02, 2022: 1.13, 2023: 0.90,
    2024: 1.05, 2025: 1.00,
}


def enso_factor(year: int) -> float:
    """Monsoon-strength multiplier for ``year`` (1.0 if unknown)."""
    return _ENSO_MONSOON_FACTOR.get(year, 1.0)


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_year(year: int) -> int:
    return 366 if _is_leap(year) else 365


def daterange(year: int) -> List[date]:
    """All calendar dates in ``year``."""
    start = date(year, 1, 1)
    return [start + timedelta(days=i) for i in range(_days_in_year(year))]


def _gamma_sample(rng: random.Random, shape: float, scale: float) -> float:
    """Gamma draw. Uses numpy if available, else ``random.gammavariate``."""
    if shape <= 0:
        return 0.0
    return rng.gammavariate(shape, scale)


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Hermite smoothstep in [0,1] (for soft spatial gradients)."""
    if edge0 == edge1:
        return 0.0 if x < edge0 else 1.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


# ──────────────────────────────────────────────────────────────────────────
# Seasonal envelopes (day-of-year → fractional driver)
# ──────────────────────────────────────────────────────────────────────────
def _monsoon_envelope(doy: int, ndays: int, onset_shift_days: float = 0.0) -> float:
    """Smooth SW-monsoon rainfall envelope in [0,1], peaking in Jul–Aug.

    A skewed Gaussian centred near day ~205 (late-Jul) with a faster rise
    (onset ~early-Jun) and a slower decay (withdrawal through Oct). The whole
    curve shifts by ``onset_shift_days`` (positive = later monsoon).
    """
    # Map to a 365-day phase regardless of leap year.
    d = (doy / ndays) * 365.0 - onset_shift_days
    peak = 205.0          # ~24 July
    rise_sigma = 26.0     # sharp onset
    fall_sigma = 45.0     # gradual withdrawal
    sigma = rise_sigma if d <= peak else fall_sigma
    val = math.exp(-((d - peak) ** 2) / (2.0 * sigma * sigma))
    # Small pre-/post-monsoon shoulder (Oct retreating rain, scattered Mar showers).
    shoulder = 0.05 * math.exp(-((d - 285.0) ** 2) / (2.0 * 30.0 ** 2))
    return max(0.0, min(1.0, val + shoulder))


def _temperature_envelope(doy: int, ndays: int) -> float:
    """Seasonal 2 m-temperature envelope in roughly [-1, 1].

    Pre-monsoon heat peak in Apr–May (~day 130), monsoon dip (cloud cover),
    winter minimum in Dec–Jan. Returns a unitless shape; callers scale it.
    """
    d = (doy / ndays) * 365.0
    # Primary annual cycle: warmest ~mid-May, coolest ~early-Jan.
    annual = math.cos(2.0 * math.pi * (d - 135.0) / 365.0)
    # Pre-monsoon spike (Apr–May) on top of the annual cycle.
    premonsoon = 0.35 * math.exp(-((d - 130.0) ** 2) / (2.0 * 22.0 ** 2))
    # Monsoon suppression (Jul–Aug) — cloudy, evaporatively cooled.
    monsoon_dip = -0.30 * math.exp(-((d - 205.0) ** 2) / (2.0 * 38.0 ** 2))
    return annual + premonsoon + monsoon_dip


# ──────────────────────────────────────────────────────────────────────────
# Spatial fields (grid-shaped, time-invariant climatic backdrops)
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _SpatialBackdrop:
    """Time-invariant spatial multipliers/offsets derived from geography."""

    wetness: List[List[float]]      # [nlat][nlon] rainfall multiplier (W wet → E dry)
    elevation: List[List[float]]    # [nlat][nlon] crude elevation (m), Ghats in west
    temp_base: List[List[float]]    # [nlat][nlon] base mean-T offset (°C) by lat+elev


def _build_backdrop(grid: GridSpec) -> _SpatialBackdrop:
    """Construct the static spatial backdrop for the pilot box.

    * **Wetness** falls off strongly from the west edge (Western Ghats orographic
      uplift) to the dry interior in the east — the defining Marathwada gradient.
    * **Elevation** is a smooth ridge in the far west (Ghats crest ~1000 m) sloping
      to the Deccan plateau (~500 m); used only as a temperature lapse proxy.
    * **temp_base** combines a south→north latitudinal gradient with the elevation
      lapse rate (~6.5 °C/km).
    """
    lats = grid.lats
    lons = grid.lons
    west, east = grid.west, grid.east

    wetness: List[List[float]] = []
    elevation: List[List[float]] = []
    temp_base: List[List[float]] = []

    lat_mid = (grid.south + grid.north) / 2.0

    for la in lats:
        wet_row: List[float] = []
        elev_row: List[float] = []
        tb_row: List[float] = []
        for lo in lons:
            # West→east position 0 (west) .. 1 (east).
            xfrac = (lo - west) / (east - west)

            # Orographic wetness: ~2.1x at the Ghats edge → ~0.55x deep interior.
            wet = 0.55 + 1.55 * (1.0 - _smoothstep(0.0, 0.85, xfrac))
            # Slight northward drying (Marathwada interior gets drier to the N).
            wet *= 1.0 - 0.12 * _smoothstep(grid.south, grid.north, la)
            wet_row.append(wet)

            # Elevation ridge in the far west, plateau elsewhere.
            ghat = 1000.0 * math.exp(-((xfrac - 0.02) ** 2) / (2.0 * 0.10 ** 2))
            plateau = 500.0 * (1.0 - 0.3 * xfrac)
            elev = max(plateau, ghat)
            elev_row.append(elev)

            # Base mean-T: warmer to the south, cooler with elevation.
            lat_term = -0.9 * (la - lat_mid)          # ~0.9 °C per degree lat
            elev_term = -6.5 * (elev / 1000.0)        # 6.5 °C/km lapse
            tb_row.append(lat_term + elev_term)

        wetness.append(wet_row)
        elevation.append(elev_row)
        temp_base.append(tb_row)

    return _SpatialBackdrop(wetness=wetness, elevation=elevation, temp_base=temp_base)


# ──────────────────────────────────────────────────────────────────────────
# Public result container
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class SyntheticYear:
    """One year of synthetic daily fields over the grid.

    Attributes are nested lists shaped ``[ntime][nlat][nlon]`` (rounded to 1
    decimal) plus the matching ``dates``. Designed to serialise straight to the
    CONTRACT.md ``fields_daily.json`` schema with no array library.
    """

    year: int
    grid: GridSpec
    dates: List[str]                 # ISO date strings
    rainfall: Cube                   # mm/day
    tmax: Cube                       # °C
    tmin: Cube                       # °C

    @property
    def ntime(self) -> int:
        return len(self.dates)


# ──────────────────────────────────────────────────────────────────────────
# Core generator
# ──────────────────────────────────────────────────────────────────────────
def generate_year(
    year: int,
    grid: GridSpec = GRID,
    *,
    seed: int = SEED,
    onset_shift_days: float = 0.0,
    backdrop: Optional[_SpatialBackdrop] = None,
    source_jitter: float = 0.0,
) -> SyntheticYear:
    """Generate one year of daily ``rainfall``/``tmax``/``tmin`` over ``grid``.

    Parameters
    ----------
    year:
        Calendar year (drives leap-day count and the ENSO-like multiplier).
    grid:
        Target :class:`~pipeline.config.GridSpec` (default = Marathwada 0.25°).
    seed:
        Base RNG seed; combined with ``year`` for reproducibility.
    onset_shift_days:
        Shift the monsoon envelope (>0 later). Used by the what-if presets and
        to create slightly different *pseudo-sources* for fusion/TC.
    backdrop:
        Pre-built spatial backdrop (built on demand if ``None``).
    source_jitter:
        Extra multiplicative noise std added per cell/day — used to synthesise
        *pseudo-independent* sources (IMD-like, IMERG-like, ERA5-Land-like) for
        the fusion + triple-collocation demonstration. ``0`` = the clean field.

    Returns
    -------
    SyntheticYear
    """
    rng = random.Random(seed * 100003 + year * 31 + int(onset_shift_days * 7))
    bd = backdrop if backdrop is not None else _build_backdrop(grid)

    nlat, nlon = grid.shape
    dates = daterange(year)
    ndays = len(dates)
    enso = enso_factor(year)

    # Pre-allocate cubes.
    if _HAVE_NUMPY:
        rain = _np.zeros((ndays, nlat, nlon), dtype=float)
        tmax = _np.zeros((ndays, nlat, nlon), dtype=float)
        tmin = _np.zeros((ndays, nlat, nlon), dtype=float)
    else:
        rain = [[[0.0] * nlon for _ in range(nlat)] for _ in range(ndays)]
        tmax = [[[0.0] * nlon for _ in range(nlat)] for _ in range(ndays)]
        tmin = [[[0.0] * nlon for _ in range(nlat)] for _ in range(ndays)]

    # Two-state Markov rainfall-occurrence chain, one per cell.
    # Transition probs depend on season (wetter season → stickier wet state).
    # wet_state[j][i] tracks whether the previous day was wet for that cell.
    wet_state = [[False] * nlon for _ in range(nlat)]

    # Regional base climate constants (°C) tuned to the Deccan interior.
    annual_mean_T = 27.0       # annual mean ~27 °C over Marathwada
    annual_amp_T = 6.5         # seasonal swing amplitude
    base_diurnal = 13.0        # dry-season Tmax−Tmin range (°C)

    for d_idx, d in enumerate(dates):
        doy = d.timetuple().tm_yday
        m_env = _monsoon_envelope(doy, ndays, onset_shift_days)   # 0..1
        t_env = _temperature_envelope(doy, ndays)                 # ~-1..1
        is_monsoon = 150 <= doy <= 290  # ~Jun 1 .. Oct 17

        # Seasonal wet/dry persistence (Markov transition probabilities).
        # Higher m_env → higher chance of staying/becoming wet.
        p_wet_given_wet = 0.45 + 0.45 * m_env      # persistence of wet spells
        p_wet_given_dry = 0.04 + 0.55 * m_env      # initiation of wet spells

        for j in range(nlat):
            for i in range(nlon):
                wet_mult = bd.wetness[j][i]

                # ---- Rainfall occurrence (Markov) ----
                prev_wet = wet_state[j][i]
                # Orographic west is wetter → bump transition probs modestly.
                bump = 0.10 * (wet_mult - 1.0)
                p = (p_wet_given_wet if prev_wet else p_wet_given_dry) + bump
                p = max(0.0, min(0.98, p))
                wet_today = rng.random() < p
                wet_state[j][i] = wet_today

                # ---- Rainfall intensity (Gamma on wet days) ----
                rain_mm = 0.0
                if wet_today and m_env > 0.01:
                    # Gamma shape/scale scaled by season, orography and ENSO.
                    shape = 0.75 + 1.4 * m_env
                    scale = (3.0 + 16.0 * m_env) * wet_mult * enso
                    rain_mm = _gamma_sample(rng, shape, scale)
                    # Occasional heavy/extreme convective day in core monsoon.
                    if is_monsoon and rng.random() < 0.02 * m_env:
                        rain_mm *= 1.8 + rng.random() * 2.2
                # Light pre/post-monsoon drizzle even on "dry-ish" days.
                elif m_env > 0.02 and rng.random() < 0.05 * m_env:
                    rain_mm = _gamma_sample(rng, 0.6, 2.5) * wet_mult

                # Optional pseudo-source jitter (for fusion/TC), multiplicative.
                if source_jitter > 0.0 and rain_mm > 0.0:
                    rain_mm *= max(0.0, 1.0 + rng.gauss(0.0, source_jitter))

                rain_mm = max(0.0, rain_mm)

                # ---- Temperature ----
                # Mean-T = regional mean + seasonal cycle + spatial base offset.
                meanT = (
                    annual_mean_T
                    + annual_amp_T * t_env
                    + bd.temp_base[j][i]
                )
                # ENSO: weak monsoon years run slightly hotter in the season.
                meanT += (1.0 - enso) * 1.5 * m_env

                # Diurnal range: wide in dry season, compressed in the monsoon.
                diurnal = base_diurnal * (1.0 - 0.55 * m_env)

                # Rain↔T anti-correlation: a wet day cools Tmax, warms Tmin.
                rain_norm = min(1.0, rain_mm / 40.0)
                tmax_anom = -4.5 * rain_norm * (1.0 if is_monsoon else 0.6)
                tmin_anom = +2.2 * rain_norm * (1.0 if is_monsoon else 0.4)

                # Daily weather noise (correlated within a day per cell).
                day_noise = rng.gauss(0.0, 1.1)

                tmax_val = meanT + diurnal / 2.0 + tmax_anom + day_noise
                tmin_val = meanT - diurnal / 2.0 + tmin_anom + day_noise * 0.6

                # Pseudo-source jitter for temperature (additive °C).
                if source_jitter > 0.0:
                    tmax_val += rng.gauss(0.0, source_jitter * 3.0)
                    tmin_val += rng.gauss(0.0, source_jitter * 3.0)

                # Physical guard: Tmin must not exceed Tmax.
                if tmin_val > tmax_val - 0.5:
                    tmin_val = tmax_val - 0.5

                if _HAVE_NUMPY:
                    rain[d_idx, j, i] = rain_mm
                    tmax[d_idx, j, i] = tmax_val
                    tmin[d_idx, j, i] = tmin_val
                else:
                    rain[d_idx][j][i] = rain_mm
                    tmax[d_idx][j][i] = tmax_val
                    tmin[d_idx][j][i] = tmin_val

    # Round to 1 decimal and convert to nested lists (contract requirement).
    rainfall_out = _round_cube(rain, ndays, nlat, nlon)
    tmax_out = _round_cube(tmax, ndays, nlat, nlon)
    tmin_out = _round_cube(tmin, ndays, nlat, nlon)

    return SyntheticYear(
        year=year,
        grid=grid,
        dates=[d.isoformat() for d in dates],
        rainfall=rainfall_out,
        tmax=tmax_out,
        tmin=tmin_out,
    )


def _round_cube(cube, ntime: int, nlat: int, nlon: int) -> Cube:
    """Round a cube (numpy array or nested list) to 1 dp nested python lists."""
    if _HAVE_NUMPY and hasattr(cube, "tolist"):
        return _np.round(cube, 1).tolist()
    out: Cube = []
    for t in range(ntime):
        plane: List[List[float]] = []
        for j in range(nlat):
            plane.append([round(cube[t][j][i], 1) for i in range(nlon)])
        out.append(plane)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Convenience: generate the representative sample year (used by run_pipeline)
# ──────────────────────────────────────────────────────────────────────────
def generate_sample_year(
    grid: GridSpec = GRID,
    year: int = TIME.sample_year,
    seed: int = SEED,
) -> SyntheticYear:
    """Generate the single representative year exported to ``fields_daily.json``."""
    return generate_year(year, grid, seed=seed)


def generate_pseudo_sources(
    year: int,
    grid: GridSpec = GRID,
    seed: int = SEED,
) -> Dict[str, SyntheticYear]:
    """Generate three *pseudo-independent* sources for fusion + triple collocation.

    These emulate the real triplet (IMD-gauge ⟂ IMERG-satellite ⟂ ERA5-Land
    reanalysis) by perturbing the clean field with different jitter / onset so
    each carries an independent error structure — exactly what triple
    collocation needs (ARCHITECTURE.md §4.3).

    Returns a dict keyed ``{"imd","imerg","era5land"}``.
    """
    bd = _build_backdrop(grid)
    return {
        # Gauge anchor: lowest noise, no onset bias.
        "imd": generate_year(year, grid, seed=seed, backdrop=bd, source_jitter=0.05),
        # Satellite (passive-MW+IR): moderate multiplicative noise, slight early bias.
        "imerg": generate_year(
            year, grid, seed=seed + 17, backdrop=bd,
            onset_shift_days=-2.0, source_jitter=0.18,
        ),
        # Reanalysis (model): drizzle-biased, smoother → larger systematic offset.
        "era5land": generate_year(
            year, grid, seed=seed + 53, backdrop=bd,
            onset_shift_days=3.0, source_jitter=0.12,
        ),
    }


__all__ = [
    "SEED",
    "Cube",
    "SyntheticYear",
    "generate_year",
    "generate_sample_year",
    "generate_pseudo_sources",
    "daterange",
    "enso_factor",
]
