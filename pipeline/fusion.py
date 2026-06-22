"""
pipeline.fusion
===============
Multi-source fusion — the heart of "use many satellites to fill each other's
gaps" (ARCHITECTURE.md §4.3, §6.1). It runs end-to-end on the synthetic
*pseudo-sources* produced by :func:`pipeline.synthetic.generate_pseudo_sources`,
and the same algorithms apply to the real harmonized sources.

Three documented stages
-----------------------
1. **Quantile-mapping bias correction** toward the IMD anchor
   (:func:`quantile_map`). Each non-anchor source's empirical CDF is matched to
   the IMD CDF per cell, correcting systematic biases (satellite IR over-/under-
   estimation, reanalysis drizzle bias).

2. **Precision-weighted Optimal-Interpolation merge** (:func:`oi_merge`). The
   bias-corrected sources are combined with weights ∝ 1/error-variance — a
   precision-weighted Bayesian / OI combine equivalent to the BLUE update used
   operationally to merge gauge + satellite rainfall.

3. **Triple collocation** (:func:`triple_collocation`). From three
   pseudo-independent sources we estimate each source's *random-error variance
   without a perfect reference*, giving the OI weights **and** a per-cell
   uncertainty field (later normalised 0..1 for ``uncertainty.json``).

Pure standard library (``math``/``statistics``); uses numpy transparently if
present. Inputs/outputs are nested-list cubes ``[ntime][nlat][nlon]``.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .synthetic import Cube, SyntheticYear

try:  # pragma: no cover
    import numpy as _np  # type: ignore

    _HAVE_NUMPY = True
except Exception:  # pragma: no cover
    _np = None  # type: ignore
    _HAVE_NUMPY = False


# ──────────────────────────────────────────────────────────────────────────
# Small column utilities (per-cell time series extraction)
# ──────────────────────────────────────────────────────────────────────────
def _cell_series(cube: Cube, j: int, i: int) -> List[float]:
    """Extract the full time series at cell (j, i) from a nested-list cube."""
    return [cube[t][j][i] for t in range(len(cube))]


def _shape(cube: Cube) -> Tuple[int, int, int]:
    ntime = len(cube)
    nlat = len(cube[0]) if ntime else 0
    nlon = len(cube[0][0]) if nlat else 0
    return ntime, nlat, nlon


# ──────────────────────────────────────────────────────────────────────────
# Stage 1 — Quantile-mapping bias correction toward the IMD anchor
# ──────────────────────────────────────────────────────────────────────────
def _empirical_quantile(sorted_vals: Sequence[float], q: float) -> float:
    """Linear-interpolated empirical quantile of an already-sorted sequence."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def _rank_fraction(sorted_vals: Sequence[float], x: float) -> float:
    """Plotting-position CDF value of ``x`` against a sorted reference."""
    n = len(sorted_vals)
    if n == 0:
        return 0.5
    # binary search for insertion point
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_vals[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    # Weibull plotting position
    return (lo + 0.5) / n


def quantile_map(source: Cube, anchor: Cube) -> Cube:
    """Bias-correct ``source`` to ``anchor`` by per-cell CDF matching.

    For each cell, the source value's CDF position (against its own distribution)
    is looked up at the same position in the anchor's distribution. This is the
    standard quantile-mapping / CDF-matching bias correction (monthly-per-cell in
    production; here per-cell over the year for the demo).

    Returns a new bias-corrected cube the same shape as ``source``.
    """
    ntime, nlat, nlon = _shape(source)
    out: Cube = [[[0.0] * nlon for _ in range(nlat)] for _ in range(ntime)]
    for j in range(nlat):
        for i in range(nlon):
            s = _cell_series(source, j, i)
            a = _cell_series(anchor, j, i)
            s_sorted = sorted(s)
            a_sorted = sorted(a)
            for t in range(ntime):
                cdf = _rank_fraction(s_sorted, s[t])
                out[t][j][i] = round(_empirical_quantile(a_sorted, cdf), 3)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Stage 3 — Triple collocation (run before OI because it sets the weights)
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class TripleCollocationResult:
    """Per-cell triple-collocation error variances for three sources.

    ``err_var[name]`` is a ``[nlat][nlon]`` field of random-error variances
    (same physical units²). ``weights[name]`` are the derived precision weights
    (∝ 1/err_var, normalised to sum to 1 per cell).
    """

    names: Tuple[str, str, str]
    err_var: Dict[str, List[List[float]]]
    weights: Dict[str, List[List[float]]]
    #: Combined per-cell uncertainty (sqrt of the precision-weighted error var).
    sigma: List[List[float]]


def triple_collocation(
    src_a: Cube, src_b: Cube, src_c: Cube,
    names: Tuple[str, str, str] = ("a", "b", "c"),
    *,
    floor: float = 1e-6,
) -> TripleCollocationResult:
    r"""Estimate per-cell random-error variances via triple collocation.

    Given three collocated measurements of the same truth with *independent*
    errors, the covariance-notation TC estimator is

        σ²_a = Cov(a,a) − Cov(a,b)·Cov(a,c) / Cov(b,c)
        σ²_b = Cov(b,b) − Cov(a,b)·Cov(b,c) / Cov(a,c)
        σ²_c = Cov(c,c) − Cov(a,c)·Cov(b,c) / Cov(a,b)

    (Stoffelen 1998; the method ESA CCI Soil Moisture is built on). It recovers
    each source's noise variance *without a perfect reference*. Negative
    estimates (from sampling noise) are floored to ``floor``.

    Precision weights ``w_i ∝ 1/σ²_i`` (normalised) feed the OI merge, and the
    precision-weighted residual variance gives a per-cell uncertainty ``sigma``.
    """
    ntime, nlat, nlon = _shape(src_a)
    na, nb, nc = names

    err_var = {na: [[0.0] * nlon for _ in range(nlat)],
               nb: [[0.0] * nlon for _ in range(nlat)],
               nc: [[0.0] * nlon for _ in range(nlat)]}
    weights = {na: [[0.0] * nlon for _ in range(nlat)],
               nb: [[0.0] * nlon for _ in range(nlat)],
               nc: [[0.0] * nlon for _ in range(nlat)]}
    sigma = [[0.0] * nlon for _ in range(nlat)]

    for j in range(nlat):
        for i in range(nlon):
            a = _cell_series(src_a, j, i)
            b = _cell_series(src_b, j, i)
            c = _cell_series(src_c, j, i)

            cov_aa = _cov(a, a)
            cov_bb = _cov(b, b)
            cov_cc = _cov(c, c)
            cov_ab = _cov(a, b)
            cov_ac = _cov(a, c)
            cov_bc = _cov(b, c)

            # Guard tiny cross-covariances (avoid div-by-zero).
            def _safe(x: float) -> float:
                return x if abs(x) > floor else (floor if x >= 0 else -floor)

            va = cov_aa - (cov_ab * cov_ac) / _safe(cov_bc)
            vb = cov_bb - (cov_ab * cov_bc) / _safe(cov_ac)
            vc = cov_cc - (cov_ac * cov_bc) / _safe(cov_ab)

            va = max(floor, va)
            vb = max(floor, vb)
            vc = max(floor, vc)

            err_var[na][j][i] = va
            err_var[nb][j][i] = vb
            err_var[nc][j][i] = vc

            # Precision weights ∝ 1/variance.
            pa, pb, pc = 1.0 / va, 1.0 / vb, 1.0 / vc
            psum = pa + pb + pc
            weights[na][j][i] = pa / psum
            weights[nb][j][i] = pb / psum
            weights[nc][j][i] = pc / psum

            # Precision-weighted analysis-error variance = 1 / Σ precisions.
            sigma[j][i] = math.sqrt(1.0 / psum)

    return TripleCollocationResult(
        names=names, err_var=err_var, weights=weights, sigma=sigma
    )


def _cov(x: Sequence[float], y: Sequence[float]) -> float:
    """Sample covariance (population-ish, /n) — stdlib, robust for short series."""
    n = len(x)
    if n == 0:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    s = 0.0
    for a, b in zip(x, y):
        s += (a - mx) * (b - my)
    return s / n


# ──────────────────────────────────────────────────────────────────────────
# Stage 2 — Precision-weighted Optimal-Interpolation merge
# ──────────────────────────────────────────────────────────────────────────
def oi_merge(
    sources: Dict[str, Cube],
    weights: Dict[str, List[List[float]]],
) -> Cube:
    """Precision-weighted merge of bias-corrected sources (OI / Bayesian BLUE).

    The analysis at each cell/day is ``x_a = Σ_i w_i · x_i`` where the per-cell
    weights ``w_i`` come from triple collocation (∝ 1/error-variance) and sum to
    1. This is the discrete precision-weighted Bayesian combine that OI / Kriging
    reduces to when sources are treated as co-located observations of one truth.

    Parameters
    ----------
    sources:
        ``{name: cube}`` of bias-corrected fields (same shape, same keys as
        ``weights``).
    weights:
        ``{name: [nlat][nlon]}`` precision weights from triple collocation.
    """
    names = list(sources.keys())
    ntime, nlat, nlon = _shape(sources[names[0]])
    out: Cube = [[[0.0] * nlon for _ in range(nlat)] for _ in range(ntime)]
    for t in range(ntime):
        for j in range(nlat):
            for i in range(nlon):
                acc = 0.0
                wsum = 0.0
                for name in names:
                    w = weights[name][j][i]
                    acc += w * sources[name][t][j][i]
                    wsum += w
                out[t][j][i] = round(acc / wsum if wsum else acc, 1)
    return out


# ──────────────────────────────────────────────────────────────────────────
# Orchestration helper: fuse one variable across pseudo-sources
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class FusedVariable:
    """Result of fusing one variable: the analysis cube + uncertainty field."""

    name: str
    analysis: Cube                         # [ntime][nlat][nlon] best estimate
    sigma: List[List[float]]               # [nlat][nlon] raw TC uncertainty (units)
    tc: TripleCollocationResult


def fuse_variable(
    var: str,
    src_imd: Cube,
    src_imerg: Cube,
    src_era5land: Cube,
) -> FusedVariable:
    """Full two-stage fusion for one variable from the 3 pseudo-sources.

    Pipeline: quantile-map IMERG & ERA5-Land to the IMD anchor → triple
    collocation on the (anchor, corrected, corrected) triplet → precision-
    weighted OI merge → return analysis + per-cell uncertainty.
    """
    # Stage 1: bias-correct the two non-anchor sources toward IMD.
    imerg_bc = quantile_map(src_imerg, src_imd)
    era5_bc = quantile_map(src_era5land, src_imd)

    # Stage 3: triple collocation (sets the weights + uncertainty).
    tc = triple_collocation(
        src_imd, imerg_bc, era5_bc,
        names=("imd", "imerg", "era5land"),
    )

    # Stage 2: precision-weighted OI merge.
    analysis = oi_merge(
        {"imd": src_imd, "imerg": imerg_bc, "era5land": era5_bc},
        tc.weights,
    )

    return FusedVariable(name=var, analysis=analysis, sigma=tc.sigma, tc=tc)


def normalize_uncertainty(sigma: List[List[float]]) -> List[List[float]]:
    """Min-max normalise a per-cell uncertainty field to 0..1 (for the UI layer).

    A twin without uncertainty is just a map (Design Principle P4): this is the
    field written to ``uncertainty.json`` and toggled as a paired layer.
    """
    flat = [v for row in sigma for v in row]
    if not flat:
        return sigma
    lo = min(flat)
    hi = max(flat)
    span = hi - lo
    if span <= 0:
        return [[0.0 for _ in row] for row in sigma]
    return [[round((v - lo) / span, 3) for v in row] for row in sigma]


__all__ = [
    "quantile_map",
    "triple_collocation",
    "TripleCollocationResult",
    "oi_merge",
    "fuse_variable",
    "FusedVariable",
    "normalize_uncertainty",
]
