"""
models.data
===========
Load / generate the multi-year training dataset, engineer features, and build
**leakage-free, year-blocked** train / validation / test splits.

Design decisions (ARCHITECTURE.md §6.4, §6.5; CONTRACT.md grid)
---------------------------------------------------------------
* **Data source.** We reuse the pipeline's physically-plausible synthetic
  generator (:mod:`pipeline.synthetic`) over the Marathwada 0.25° grid
  (14×20 = 280 cells). It encodes monsoon seasonality, a west→east wetness
  gradient, rain↔temperature anti-correlation, wet/dry Markov spells and an
  ENSO-like interannual multiplier — enough real structure that learned models
  can genuinely beat persistence/climatology. If the import ever fails we fall
  back to an equivalent in-module generator so this module still runs.
* **Multi-year.** We generate ~20 years (default 2006–2025) of daily fields so
  there is real interannual variability to learn and to hold out.
* **Year-blocked split (NEVER random k-fold).** Random splitting leaks temporal
  autocorrelation and understates error by up to 70–80 % (ARCHITECTURE.md §6.5).
  We split by *whole calendar years*: the last ``n_test`` years are the test
  set, the preceding ``n_val`` years are validation, the rest are training. A
  one-day embargo at year boundaries is implicit because features use only past
  lags within a contiguous daily series and each split is a distinct year span.
* **Task.** Next-day (lead-1) prediction of rainfall / tmax / tmin per cell from
  features available at day *t*. Multi-lead forecasts are produced recursively
  in :mod:`models.predict`.

Feature engineering (ARCHITECTURE.md §6.2 "lags, climatology, harmonics, neighbours, lat/lon")
----------------------------------------------------------------------------------------------
Per (day t, cell) the feature vector for predicting variable *v* at t+1 is:

* lagged values of *all three* variables at t, t-1, t-2 (k=3 lags),
* day-of-year sin/cos harmonics (annual + semi-annual) — the seasonal cycle,
* 4-neighbour mean of the *target* variable at t (spatial context),
* normalised lat / lon (cell location),
* recent rainfall accumulation (3-day and 7-day running sums at t),
* the cell's daily climatological value for the *target* day (t+1 day-of-year),
  computed from the **training years only** (no leakage).

Everything is plain numpy; the module degrades to nested-list math only inside
the generator fallback. numpy is required for the feature matrices (it is part
of the always-available scientific stack here).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# ---- Reuse the pipeline generator + grid (graceful fallback if unavailable) --
_PIPELINE_OK = True
try:  # pragma: no cover - exercised when the pipeline package is importable
    from pipeline.config import GRID as _GRID  # type: ignore
    from pipeline.synthetic import SEED as _SEED  # type: ignore
    from pipeline.synthetic import generate_year as _gen_year  # type: ignore
except Exception:  # pragma: no cover
    _PIPELINE_OK = False
    _GRID = None  # type: ignore
    _SEED = 20260621


# Variable order used everywhere downstream.
VARS: Tuple[str, str, str] = ("rainfall", "tmax", "tmin")

# Number of autoregressive lags used as features.
N_LAGS: int = 3

# Default multi-year window: 20 years, hold out the last 3 for testing.
DEFAULT_YEARS: Tuple[int, ...] = tuple(range(2006, 2026))  # 2006..2025
DEFAULT_N_TEST: int = 3
DEFAULT_N_VAL: int = 2


# ──────────────────────────────────────────────────────────────────────────
# Grid abstraction (works with the pipeline GridSpec or a tiny local stand-in)
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GridInfo:
    """Minimal grid description the models need (lat/lon centres + shape)."""

    nlat: int
    nlon: int
    lats: List[float]
    lons: List[float]
    bbox: Tuple[float, float, float, float]  # (W, S, E, N)
    res_deg: float

    @property
    def shape(self) -> Tuple[int, int]:
        return (self.nlat, self.nlon)


def _marathwada_grid() -> GridInfo:
    """Marathwada 0.25° grid — from the pipeline if present, else replicated."""
    if _PIPELINE_OK and _GRID is not None:
        return GridInfo(
            nlat=_GRID.nlat,
            nlon=_GRID.nlon,
            lats=list(_GRID.lats),
            lons=list(_GRID.lons),
            bbox=tuple(_GRID.bbox),  # type: ignore[arg-type]
            res_deg=_GRID.res_deg,
        )
    # Replicated definition (CONTRACT.md): bbox [74.0,17.5,79.0,21.0], 0.25°.
    west, south, east, north, res = 74.0, 17.5, 79.0, 21.0, 0.25
    nlon = int(round((east - west) / res))   # 20
    nlat = int(round((north - south) / res))  # 14
    half = res / 2.0
    lons = [round(west + half + i * res, 6) for i in range(nlon)]
    lats = [round(south + half + j * res, 6) for j in range(nlat)]
    return GridInfo(nlat=nlat, nlon=nlon, lats=lats, lons=lons,
                    bbox=(west, south, east, north), res_deg=res)


GRID: GridInfo = _marathwada_grid()


# ──────────────────────────────────────────────────────────────────────────
# Fallback generator (only used if pipeline.synthetic cannot be imported)
# ──────────────────────────────────────────────────────────────────────────
def _fallback_generate_year(year: int, grid: GridInfo, seed: int) -> Dict[str, np.ndarray]:
    """A compact equivalent of pipeline.synthetic.generate_year (numpy).

    Encodes the same qualitative physics (monsoon envelope, W→E wetness,
    rain↔T anti-correlation, ENSO-like multiplier, wet/dry persistence) so the
    learned models still have real structure to exploit. Only invoked when the
    pipeline import fails.
    """
    import random as _random

    rng = _random.Random(seed * 100003 + year * 31)
    ndays = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    nlat, nlon = grid.nlat, grid.nlon
    enso = {2009: 0.78, 2015: 0.76, 2016: 1.12, 2022: 1.13}.get(year, 1.0)

    # Static spatial backdrop.
    west, east = grid.bbox[0], grid.bbox[2]
    south, north = grid.bbox[1], grid.bbox[3]
    wet = np.zeros((nlat, nlon))
    tbase = np.zeros((nlat, nlon))
    lat_mid = (south + north) / 2.0
    for j, la in enumerate(grid.lats):
        for i, lo in enumerate(grid.lons):
            xf = (lo - west) / (east - west)
            t = max(0.0, min(1.0, xf / 0.85))
            smooth = t * t * (3.0 - 2.0 * t)
            wet[j, i] = (0.55 + 1.55 * (1.0 - smooth)) * (1.0 - 0.12 * ((la - south) / (north - south)))
            elev = max(500.0 * (1.0 - 0.3 * xf), 1000.0 * math.exp(-((xf - 0.02) ** 2) / (2 * 0.10 ** 2)))
            tbase[j, i] = -0.9 * (la - lat_mid) - 6.5 * (elev / 1000.0)

    rain = np.zeros((ndays, nlat, nlon))
    tmax = np.zeros((ndays, nlat, nlon))
    tmin = np.zeros((ndays, nlat, nlon))
    wet_state = np.zeros((nlat, nlon), dtype=bool)
    for d in range(ndays):
        doy = d + 1
        dd = (doy / ndays) * 365.0
        sig = 26.0 if dd <= 205 else 45.0
        m_env = max(0.0, min(1.0, math.exp(-((dd - 205.0) ** 2) / (2 * sig * sig))))
        annual = math.cos(2 * math.pi * (dd - 135.0) / 365.0)
        premon = 0.35 * math.exp(-((dd - 130.0) ** 2) / (2 * 22.0 ** 2))
        mdip = -0.30 * math.exp(-((dd - 205.0) ** 2) / (2 * 38.0 ** 2))
        t_env = annual + premon + mdip
        is_mon = 150 <= doy <= 290
        p_ww = 0.45 + 0.45 * m_env
        p_wd = 0.04 + 0.55 * m_env
        for j in range(nlat):
            for i in range(nlon):
                wm = wet[j, i]
                p = (p_ww if wet_state[j, i] else p_wd) + 0.10 * (wm - 1.0)
                p = max(0.0, min(0.98, p))
                wt = rng.random() < p
                wet_state[j, i] = wt
                r = 0.0
                if wt and m_env > 0.01:
                    shape = 0.75 + 1.4 * m_env
                    scale = (3.0 + 16.0 * m_env) * wm * enso
                    r = rng.gammavariate(shape, scale)
                    if is_mon and rng.random() < 0.02 * m_env:
                        r *= 1.8 + rng.random() * 2.2
                elif m_env > 0.02 and rng.random() < 0.05 * m_env:
                    r = rng.gammavariate(0.6, 2.5) * wm
                r = max(0.0, r)
                meanT = 27.0 + 6.5 * t_env + tbase[j, i] + (1.0 - enso) * 1.5 * m_env
                diur = 13.0 * (1.0 - 0.55 * m_env)
                rn = min(1.0, r / 40.0)
                noise = rng.gauss(0.0, 1.1)
                tx = meanT + diur / 2.0 - 4.5 * rn * (1.0 if is_mon else 0.6) + noise
                tn = meanT - diur / 2.0 + 2.2 * rn * (1.0 if is_mon else 0.4) + noise * 0.6
                if tn > tx - 0.5:
                    tn = tx - 0.5
                rain[d, j, i] = r
                tmax[d, j, i] = tx
                tmin[d, j, i] = tn
    return {"rainfall": np.round(rain, 1), "tmax": np.round(tmax, 1), "tmin": np.round(tmin, 1)}


def _generate_year_arrays(year: int, grid: GridInfo, seed: int) -> Dict[str, np.ndarray]:
    """Return {var: (ndays, nlat, nlon)} for one year, via pipeline or fallback."""
    if _PIPELINE_OK:
        sy = _gen_year(year, seed=seed)  # type: ignore[misc]
        return {
            "rainfall": np.asarray(sy.rainfall, dtype=float),
            "tmax": np.asarray(sy.tmax, dtype=float),
            "tmin": np.asarray(sy.tmin, dtype=float),
        }
    return _fallback_generate_year(year, grid, seed)


# ──────────────────────────────────────────────────────────────────────────
# Dataset container
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class ClimateDataset:
    """A contiguous multi-year daily cube plus its year axis and split masks.

    Arrays are shaped ``( T, nlat, nlon)`` with ``T`` = total days across all
    years, time ascending. ``year_of_day`` gives each day's calendar year.
    """

    grid: GridInfo
    years: List[int]
    dates: List[str]                 # ISO date per day, length T
    year_of_day: np.ndarray          # (T,) int
    rainfall: np.ndarray             # (T, nlat, nlon)
    tmax: np.ndarray
    tmin: np.ndarray
    train_years: List[int]
    val_years: List[int]
    test_years: List[int]

    @property
    def T(self) -> int:
        return self.rainfall.shape[0]

    def cube(self, var: str) -> np.ndarray:
        return getattr(self, var)

    def split_of_year(self, y: int) -> str:
        if y in self.test_years:
            return "test"
        if y in self.val_years:
            return "val"
        return "train"


def load_dataset(
    years: Sequence[int] = DEFAULT_YEARS,
    n_test: int = DEFAULT_N_TEST,
    n_val: int = DEFAULT_N_VAL,
    grid: GridInfo = GRID,
    seed: int = _SEED,
) -> ClimateDataset:
    """Generate / load the multi-year daily dataset and define year-blocked splits."""
    years = list(years)
    years.sort()
    per_year: Dict[int, Dict[str, np.ndarray]] = {
        y: _generate_year_arrays(y, grid, seed) for y in years
    }

    # Concatenate along time, tracking the per-day year and date string.
    rain_parts, tmax_parts, tmin_parts = [], [], []
    year_of_day: List[int] = []
    dates: List[str] = []
    from datetime import date, timedelta
    for y in years:
        arrs = per_year[y]
        nd = arrs["rainfall"].shape[0]
        rain_parts.append(arrs["rainfall"])
        tmax_parts.append(arrs["tmax"])
        tmin_parts.append(arrs["tmin"])
        year_of_day.extend([y] * nd)
        d0 = date(y, 1, 1)
        dates.extend([(d0 + timedelta(days=i)).isoformat() for i in range(nd)])

    rainfall = np.concatenate(rain_parts, axis=0)
    tmax = np.concatenate(tmax_parts, axis=0)
    tmin = np.concatenate(tmin_parts, axis=0)

    test_years = years[-n_test:]
    val_years = years[-(n_test + n_val):-n_test]
    train_years = years[:-(n_test + n_val)]

    return ClimateDataset(
        grid=grid,
        years=years,
        dates=dates,
        year_of_day=np.asarray(year_of_day, dtype=int),
        rainfall=rainfall,
        tmax=tmax,
        tmin=tmin,
        train_years=train_years,
        val_years=val_years,
        test_years=test_years,
    )


# ──────────────────────────────────────────────────────────────────────────
# Daily climatology (computed on TRAIN years only — no leakage)
# ──────────────────────────────────────────────────────────────────────────
def daily_climatology(ds: ClimateDataset, var: str, ref_years: Sequence[int]) -> np.ndarray:
    """Return a (366, nlat, nlon) day-of-year climatology from ``ref_years``.

    Day-of-year is 1..366; Feb-29 (doy 60 in leap years) is filled from
    neighbours when a reference year is non-leap. A light 15-day circular
    smoothing removes sampling noise so it is a fair, smooth seasonal baseline.
    """
    nlat, nlon = ds.grid.shape
    cube = ds.cube(var)
    ref = set(int(y) for y in ref_years)
    sums = np.zeros((366, nlat, nlon))
    counts = np.zeros((366, 1, 1))
    # Recover day-of-year per day from the date strings.
    from datetime import date
    for t in range(ds.T):
        if int(ds.year_of_day[t]) not in ref:
            continue
        iso = ds.dates[t]
        yy, mm, dd = (int(x) for x in iso.split("-"))
        doy = date(yy, mm, dd).timetuple().tm_yday
        sums[doy - 1] += cube[t]
        counts[doy - 1, 0, 0] += 1
    counts[counts == 0] = 1.0
    clim = sums / counts
    # Fill any empty doy (e.g. 366 with no leap ref year) by nearest non-empty.
    empty = (counts[:, 0, 0] == 1.0) & (sums.reshape(366, -1).sum(axis=1) == 0)
    for d in np.where(empty)[0]:
        for off in range(1, 8):
            if not empty[(d - off) % 366]:
                clim[d] = clim[(d - off) % 366]
                break
    # Circular 15-day smoothing.
    k = 15
    pad = np.concatenate([clim[-k:], clim, clim[:k]], axis=0)
    kernel = np.ones(2 * k + 1) / (2 * k + 1)
    smoothed = np.empty_like(clim)
    for j in range(nlat):
        for i in range(nlon):
            smoothed[:, j, i] = np.convolve(pad[:, j, i], kernel, mode="same")[k:-k]
    return smoothed


def doy_of(ds: ClimateDataset, t: int) -> int:
    """Day-of-year (1..366) for global time index ``t``.

    Tolerates ``t == len(dates)`` (exactly one day past the end) by extrapolating
    from the last available date — this is the recursive-forecast roll-forward
    case where the target day is not yet on the rolling time axis.
    """
    from datetime import date, timedelta
    dates = ds.dates
    if t >= len(dates):
        yy, mm, dd = (int(x) for x in dates[-1].split("-"))
        return (date(yy, mm, dd) + timedelta(days=(t - len(dates) + 1))).timetuple().tm_yday
    yy, mm, dd = (int(x) for x in dates[t].split("-"))
    return date(yy, mm, dd).timetuple().tm_yday


# ──────────────────────────────────────────────────────────────────────────
# Feature engineering for next-day per-cell prediction
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class FeatureSpec:
    """Names + slices describing the engineered feature matrix columns."""

    names: List[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.names)


def _neighbour_mean(field_t: np.ndarray) -> np.ndarray:
    """4-neighbour mean of a single (nlat, nlon) field (edge-replicated)."""
    up = np.empty_like(field_t); up[1:] = field_t[:-1]; up[0] = field_t[0]
    dn = np.empty_like(field_t); dn[:-1] = field_t[1:]; dn[-1] = field_t[-1]
    lf = np.empty_like(field_t); lf[:, 1:] = field_t[:, :-1]; lf[:, 0] = field_t[:, 0]
    rt = np.empty_like(field_t); rt[:, :-1] = field_t[:, 1:]; rt[:, -1] = field_t[:, -1]
    return (up + dn + lf + rt) / 4.0


def build_feature_table(
    ds: ClimateDataset,
    target_var: str,
    clim: Dict[str, np.ndarray],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, FeatureSpec]:
    """Build (X, y, day_index, cell_index, spec) for predicting ``target_var`` at t+1.

    A sample exists for every (t, cell) where t and t+1 lie in the **same
    calendar year** (so lags/targets never cross a year discontinuity — this is
    the embargo that keeps the year-blocked split clean) and t has ``N_LAGS``
    valid history days within that year.

    Returns
    -------
    X : (N, F) float feature matrix
    y : (N,) target = ``target_var`` at day t+1
    day_index : (N,) the global time index t of each sample (the t+1 target is t+1)
    cell_index : (N,) flattened cell id  (j*nlon + i)
    spec : FeatureSpec with the column names
    """
    nlat, nlon = ds.grid.shape
    ncell = nlat * nlon
    lat_arr = np.asarray(ds.grid.lats)[:, None]            # (nlat,1)
    lon_arr = np.asarray(ds.grid.lons)[None, :]            # (1,nlon)
    lat_norm = ((lat_arr - lat_arr.min()) / max(1e-9, (lat_arr.max() - lat_arr.min())))
    lon_norm = ((lon_arr - lon_arr.min()) / max(1e-9, (lon_arr.max() - lon_arr.min())))
    lat_flat = np.broadcast_to(lat_norm, (nlat, nlon)).reshape(-1)
    lon_flat = np.broadcast_to(lon_norm, (nlat, nlon)).reshape(-1)

    rain = ds.rainfall
    cubes = {"rainfall": ds.rainfall, "tmax": ds.tmax, "tmin": ds.tmin}

    # Precompute rolling rainfall accumulation (3d, 7d) along time.
    def _roll_sum(arr: np.ndarray, w: int) -> np.ndarray:
        out = np.zeros_like(arr)
        acc = np.zeros((nlat, nlon))
        from collections import deque
        buf: "deque[np.ndarray]" = deque()
        for t in range(arr.shape[0]):
            buf.append(arr[t]); acc += arr[t]
            if len(buf) > w:
                acc -= buf.popleft()
            out[t] = acc
        return out

    rain_acc3 = _roll_sum(rain, 3)
    rain_acc7 = _roll_sum(rain, 7)

    # Column layout.
    spec = FeatureSpec()
    for lag in range(N_LAGS):
        for v in VARS:
            spec.names.append(f"{v}_lag{lag}")
    spec.names += ["doy_sin", "doy_cos", "doy_sin2", "doy_cos2"]
    spec.names += [f"{target_var}_nbr"]
    spec.names += ["lat", "lon"]
    spec.names += ["rain_acc3", "rain_acc7"]
    spec.names += [f"{target_var}_clim_next"]

    rows_X: List[np.ndarray] = []
    rows_y: List[np.ndarray] = []
    rows_t: List[np.ndarray] = []
    rows_c: List[np.ndarray] = []

    target_cube = cubes[target_var]
    clim_t = clim[target_var]  # (366, nlat, nlon)

    # Iterate per year so lags/targets stay within a year.
    from datetime import date
    year_starts: Dict[int, int] = {}
    for t in range(ds.T):
        y = int(ds.year_of_day[t])
        if y not in year_starts:
            year_starts[y] = t

    for y in ds.years:
        idx = np.where(ds.year_of_day == y)[0]
        t0, t1 = int(idx[0]), int(idx[-1])
        # Need N_LAGS-1 history before t and a t+1 within the same year.
        for t in range(t0 + (N_LAGS - 1), t1):  # t1 excluded so t+1<=t1
            feat_planes: List[np.ndarray] = []
            for lag in range(N_LAGS):
                tt = t - lag
                for v in VARS:
                    feat_planes.append(cubes[v][tt].reshape(-1))
            # Day-of-year harmonics of the *target* day t+1.
            tgt_doy = doy_of(ds, t + 1)
            ang = 2 * math.pi * (tgt_doy / 366.0)
            harm = [math.sin(ang), math.cos(ang), math.sin(2 * ang), math.cos(2 * ang)]
            harm_planes = [np.full(ncell, h) for h in harm]
            nbr = _neighbour_mean(target_cube[t]).reshape(-1)
            acc3 = rain_acc3[t].reshape(-1)
            acc7 = rain_acc7[t].reshape(-1)
            clim_next = clim_t[tgt_doy - 1].reshape(-1)

            cols = feat_planes + harm_planes + [nbr, lat_flat, lon_flat, acc3, acc7, clim_next]
            X = np.stack(cols, axis=1)  # (ncell, F)
            y_t = target_cube[t + 1].reshape(-1)

            rows_X.append(X)
            rows_y.append(y_t)
            rows_t.append(np.full(ncell, t, dtype=int))
            rows_c.append(np.arange(ncell, dtype=int))

    X = np.concatenate(rows_X, axis=0)
    y = np.concatenate(rows_y, axis=0)
    tix = np.concatenate(rows_t, axis=0)
    cix = np.concatenate(rows_c, axis=0)
    return X, y, tix, cix, spec


def split_masks(ds: ClimateDataset, day_index: np.ndarray) -> Dict[str, np.ndarray]:
    """Boolean masks selecting train / val / test rows by the day's year."""
    yrs = ds.year_of_day[day_index]
    train = np.isin(yrs, ds.train_years)
    val = np.isin(yrs, ds.val_years)
    test = np.isin(yrs, ds.test_years)
    return {"train": train, "val": val, "test": test}


# Convenience: build everything for all three variables in one call.
@dataclass
class PreparedData:
    ds: ClimateDataset
    clim: Dict[str, np.ndarray]                 # var -> (366,nlat,nlon) (train-only)
    tables: Dict[str, Dict[str, np.ndarray]]    # var -> {X,y,t,c, masks...}
    spec: Dict[str, FeatureSpec]


def prepare(ds: Optional[ClimateDataset] = None, **kw) -> PreparedData:
    """Load data (if needed), compute train-only climatology, and build tables."""
    if ds is None:
        ds = load_dataset(**kw)
    clim = {v: daily_climatology(ds, v, ds.train_years) for v in VARS}
    tables: Dict[str, Dict[str, np.ndarray]] = {}
    spec: Dict[str, FeatureSpec] = {}
    for v in VARS:
        X, y, tix, cix, sp = build_feature_table(ds, v, clim)
        masks = split_masks(ds, tix)
        tables[v] = {"X": X, "y": y, "t": tix, "c": cix, **masks}
        spec[v] = sp
    return PreparedData(ds=ds, clim=clim, tables=tables, spec=spec)


__all__ = [
    "VARS",
    "N_LAGS",
    "GRID",
    "GridInfo",
    "ClimateDataset",
    "PreparedData",
    "FeatureSpec",
    "load_dataset",
    "daily_climatology",
    "build_feature_table",
    "split_masks",
    "prepare",
    "doy_of",
]
