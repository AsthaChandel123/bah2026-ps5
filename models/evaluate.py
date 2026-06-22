"""
models.evaluate
===============
Honest verification metrics for the Bharat Climate Twin forecasts
(ARCHITECTURE.md §15, research/03 §15). Pure numpy — always runnable.

Deterministic (temperature + rainfall continuous)
    RMSE, MAE, bias (mean error), Pearson correlation, R².

Precipitation categorical (IMD thresholds 1 / 10 / 50 mm/day)
    From the 2×2 contingency table (hits H, misses M, false alarms F):
    POD = H/(H+M), FAR = F/(H+F), CSI = H/(H+M+F).

Probabilistic / ensemble
    CRPS (Gaussian closed-form from a predictive mean+sigma; equals MAE in the
    sigma→0 limit so it is comparable to the deterministic members), and
    coverage + mean width of central prediction intervals.

Skill score
    skill = 1 − metric_model / metric_reference  (reference = climatology),
    reported for RMSE so positive = better than climatology.

All functions ignore NaNs pairwise and return plain Python floats so the output
serialises straight to JSON.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np

# IMD daily-rainfall categorical thresholds used for CSI/POD/FAR (mm/day).
RAIN_THRESHOLDS: tuple = (1.0, 10.0, 50.0)


def _finite_pair(yhat: np.ndarray, y: np.ndarray) -> tuple:
    yhat = np.asarray(yhat, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    m = np.isfinite(yhat) & np.isfinite(y)
    return yhat[m], y[m]


def rmse(yhat: np.ndarray, y: np.ndarray) -> float:
    a, b = _finite_pair(yhat, y)
    if a.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean((a - b) ** 2)))


def mae(yhat: np.ndarray, y: np.ndarray) -> float:
    a, b = _finite_pair(yhat, y)
    if a.size == 0:
        return float("nan")
    return float(np.mean(np.abs(a - b)))


def bias(yhat: np.ndarray, y: np.ndarray) -> float:
    """Mean error (forecast − obs); positive = over-prediction."""
    a, b = _finite_pair(yhat, y)
    if a.size == 0:
        return float("nan")
    return float(np.mean(a - b))


def correlation(yhat: np.ndarray, y: np.ndarray) -> float:
    a, b = _finite_pair(yhat, y)
    if a.size < 2:
        return float("nan")
    sa, sb = a.std(), b.std()
    if sa < 1e-12 or sb < 1e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def r2(yhat: np.ndarray, y: np.ndarray) -> float:
    a, b = _finite_pair(yhat, y)
    if a.size < 2:
        return float("nan")
    ss_res = np.sum((b - a) ** 2)
    ss_tot = np.sum((b - b.mean()) ** 2)
    if ss_tot < 1e-12:
        return float("nan")
    return float(1.0 - ss_res / ss_tot)


def contingency(yhat: np.ndarray, y: np.ndarray, thr: float) -> Dict[str, int]:
    """2×2 contingency counts for the event (value >= thr)."""
    a, b = _finite_pair(yhat, y)
    pf = a >= thr
    po = b >= thr
    H = int(np.sum(pf & po))
    F = int(np.sum(pf & ~po))
    M = int(np.sum(~pf & po))
    N = int(np.sum(~pf & ~po))
    return {"H": H, "F": F, "M": M, "N": N}


def csi_pod_far(yhat: np.ndarray, y: np.ndarray, thr: float) -> Dict[str, float]:
    """CSI / POD / FAR / frequency-bias for one threshold."""
    c = contingency(yhat, y, thr)
    H, F, M = c["H"], c["F"], c["M"]
    pod = H / (H + M) if (H + M) > 0 else float("nan")
    far = F / (H + F) if (H + F) > 0 else float("nan")
    csi = H / (H + M + F) if (H + M + F) > 0 else float("nan")
    freq_bias = (H + F) / (H + M) if (H + M) > 0 else float("nan")
    return {"CSI": csi, "POD": pod, "FAR": far, "freq_bias": freq_bias}


def categorical_table(yhat: np.ndarray, y: np.ndarray,
                      thresholds: Sequence[float] = RAIN_THRESHOLDS) -> Dict[str, Dict[str, float]]:
    """CSI/POD/FAR at each threshold, keyed by the threshold string."""
    out: Dict[str, Dict[str, float]] = {}
    for thr in thresholds:
        key = f"{thr:g}mm"
        out[key] = csi_pod_far(yhat, y, thr)
    return out


def crps_gaussian(mu: np.ndarray, sigma: np.ndarray, y: np.ndarray) -> float:
    """Closed-form CRPS for a Gaussian predictive distribution N(mu, sigma²).

    CRPS(N(mu,sig), y) = sig * [ z(2Φ(z)-1) + 2φ(z) - 1/√π ],  z=(y-mu)/sig.
    A small floor on sigma keeps it finite; as sigma→0 this tends to |y-mu|,
    so it is directly comparable to the deterministic MAE.
    """
    mu = np.asarray(mu, dtype=float).reshape(-1)
    sigma = np.asarray(sigma, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    m = np.isfinite(mu) & np.isfinite(sigma) & np.isfinite(y)
    mu, sigma, y = mu[m], sigma[m], y[m]
    if mu.size == 0:
        return float("nan")
    sigma = np.maximum(sigma, 1e-3)
    z = (y - mu) / sigma
    # Standard normal CDF/PDF.
    Phi = 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))
    phi = np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    crps = sigma * (z * (2.0 * Phi - 1.0) + 2.0 * phi - 1.0 / math.sqrt(math.pi))
    return float(np.mean(crps))


def interval_coverage(lower: np.ndarray, upper: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    """Empirical coverage and mean width of [lower, upper] prediction intervals."""
    lo = np.asarray(lower, dtype=float).reshape(-1)
    hi = np.asarray(upper, dtype=float).reshape(-1)
    yy = np.asarray(y, dtype=float).reshape(-1)
    m = np.isfinite(lo) & np.isfinite(hi) & np.isfinite(yy)
    lo, hi, yy = lo[m], hi[m], yy[m]
    if yy.size == 0:
        return {"coverage": float("nan"), "width": float("nan")}
    inside = (yy >= lo) & (yy <= hi)
    return {"coverage": float(np.mean(inside)), "width": float(np.mean(hi - lo))}


def deterministic_metrics(yhat: np.ndarray, y: np.ndarray, var: str) -> Dict[str, object]:
    """Full deterministic metric bundle for one variable.

    Includes categorical CSI/POD/FAR only for rainfall (else the ``CSI`` key is
    ``None`` so the JSON schema is uniform across variables).
    """
    out: Dict[str, object] = {
        "RMSE": round(rmse(yhat, y), 4),
        "MAE": round(mae(yhat, y), 4),
        "bias": round(bias(yhat, y), 4),
        "corr": round(correlation(yhat, y), 4),
        "R2": round(r2(yhat, y), 4),
    }
    if var == "rainfall":
        cat = categorical_table(yhat, y)
        out["categorical"] = {
            k: {kk: (round(vv, 4) if vv == vv else None) for kk, vv in v.items()}
            for k, v in cat.items()
        }
        # Headline CSI at the 1 mm wet/dry threshold for the summary table.
        out["CSI"] = out["categorical"]["1mm"]["CSI"]
    else:
        out["CSI"] = None
    return out


def skill_score(metric_model: float, metric_ref: float) -> float:
    """skill = 1 − model/ref. Positive ⇒ model beats the reference baseline."""
    if metric_ref is None or not np.isfinite(metric_ref) or metric_ref < 1e-12:
        return float("nan")
    if metric_model is None or not np.isfinite(metric_model):
        return float("nan")
    return float(1.0 - metric_model / metric_ref)


__all__ = [
    "RAIN_THRESHOLDS",
    "rmse", "mae", "bias", "correlation", "r2",
    "contingency", "csi_pod_far", "categorical_table",
    "crps_gaussian", "interval_coverage",
    "deterministic_metrics", "skill_score",
]
