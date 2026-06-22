"""
models.ensemble
===============
The consensus engine (ARCHITECTURE.md §6.3, research/03 §14):

1. **Ridge / linear regression** (pure numpy) — used two ways:
   * as an additional *base learner* on the engineered features, and
   * as the *stacking meta-learner* that blends base-member predictions.
2. **Stacked generalization** — a ridge meta-model fit on the **validation**
   predictions of the base members (out-of-training, no leakage), producing a
   blended mean forecast.
3. **EMOS / NGR calibration** — affine calibration of the blended mean and a
   variance model ``sigma² = a + b · spread²`` fit by minimising CRPS on the
   validation set (the operational distributional post-processor; Gaussian for
   temperature, Gaussian-on-nonneg for rainfall).
4. **Conformal prediction** — split-conformal intervals: take the validation
   absolute residuals (optionally normalised by the EMOS sigma) and use their
   empirical ``(1-alpha)`` quantile as the half-width, giving **distribution-free
   coverage** at the target level on the test set.

Everything here is numpy-only so the combiner always runs, even when no ML
library is installed and the only base members are the numpy baselines + analog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import evaluate


# ──────────────────────────────────────────────────────────────────────────
# Ridge regression (numpy) — base learner AND stacking meta-learner
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class Ridge:
    """L2-regularised linear regression with standardised inputs.

    Closed-form solve of ``(XᵀX + λI) w = Xᵀy`` on z-scored features (the bias
    is handled by centring y). ``nonneg`` clamps predictions at 0 (rainfall).
    """

    alpha: float = 1.0
    nonneg: bool = False
    w: Optional[np.ndarray] = None
    x_mu: Optional[np.ndarray] = None
    x_sd: Optional[np.ndarray] = None
    y_mu: float = 0.0
    resid_sigma: float = 1.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "Ridge":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        self.x_mu = X.mean(axis=0)
        self.x_sd = X.std(axis=0)
        self.x_sd[self.x_sd < 1e-9] = 1.0
        Xz = (X - self.x_mu) / self.x_sd
        self.y_mu = float(y.mean())
        yc = y - self.y_mu
        n_feat = Xz.shape[1]
        A = Xz.T @ Xz + self.alpha * np.eye(n_feat)
        b = Xz.T @ yc
        self.w = np.linalg.solve(A, b)
        resid = y - self.predict(X)
        self.resid_sigma = float(np.std(resid)) if resid.size else 1.0
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        Xz = (X - self.x_mu) / self.x_sd
        pred = Xz @ self.w + self.y_mu
        if self.nonneg:
            pred = np.maximum(pred, 0.0)
        return pred


# ──────────────────────────────────────────────────────────────────────────
# EMOS / NGR calibration of a blended mean + spread → (mu, sigma)
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class EMOS:
    """Affine mean + linear-in-variance spread calibration by min-CRPS.

    mu_cal   = c0 + c1 * mean
    sigma²   = max(d0, 0) + max(d1, 0) * spread²

    Parameters are fit by a small coordinate search minimising mean Gaussian
    CRPS on validation pairs (robust and dependency-free; no scipy optimiser
    needed). ``nonneg`` clamps the calibrated mean (rainfall).
    """

    c0: float = 0.0
    c1: float = 1.0
    d0: float = 1.0
    d1: float = 1.0
    nonneg: bool = False

    def apply(self, mean: np.ndarray, spread: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        mu = self.c0 + self.c1 * np.asarray(mean, dtype=float)
        if self.nonneg:
            mu = np.maximum(mu, 0.0)
        var = np.maximum(self.d0, 1e-6) + np.maximum(self.d1, 0.0) * np.asarray(spread, dtype=float) ** 2
        sigma = np.sqrt(np.maximum(var, 1e-6))
        return mu, sigma

    def fit(self, mean: np.ndarray, spread: np.ndarray, y: np.ndarray) -> "EMOS":
        mean = np.asarray(mean, dtype=float)
        spread = np.asarray(spread, dtype=float)
        y = np.asarray(y, dtype=float)
        # --- mean affine fit by least squares (c0, c1) ---
        A = np.stack([np.ones_like(mean), mean], axis=1)
        coef, *_ = np.linalg.lstsq(A, y, rcond=None)
        self.c0, self.c1 = float(coef[0]), float(coef[1])
        resid = y - (self.c0 + self.c1 * mean)
        base_var = float(np.var(resid))
        # --- spread calibration: search d0, d1 minimising CRPS ---
        sp2 = spread ** 2
        sp2_mean = float(np.mean(sp2)) if sp2.size else 1.0
        best = (base_var, 0.0)
        best_crps = float("inf")
        d0_grid = [base_var * f for f in (0.1, 0.25, 0.5, 0.75, 1.0)]
        # scale d1 so d1*mean(sp2) spans a sensible fraction of base_var
        if sp2_mean > 1e-9:
            d1_grid = [0.0] + [base_var * f / sp2_mean for f in (0.25, 0.5, 1.0, 2.0)]
        else:
            d1_grid = [0.0]
        for d0 in d0_grid:
            for d1 in d1_grid:
                var = np.maximum(d0, 1e-6) + d1 * sp2
                sigma = np.sqrt(np.maximum(var, 1e-6))
                c = evaluate.crps_gaussian(self.c0 + self.c1 * mean, sigma, y)
                if c < best_crps:
                    best_crps = c
                    best = (d0, d1)
        self.d0, self.d1 = float(best[0]), float(best[1])
        return self


# ──────────────────────────────────────────────────────────────────────────
# Split-conformal prediction intervals
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class Conformal:
    """Split-conformal half-width from validation residuals.

    If ``normalized`` and a sigma is supplied, the nonconformity score is
    ``|y-mu|/sigma`` and the interval half-width at a test point is
    ``q * sigma`` (locally-adaptive). Otherwise the half-width is the constant
    residual quantile ``q``. Guarantees ≈ ``1-alpha`` marginal coverage under
    exchangeability (we use a temporally-blocked calibration set — the whole
    validation *years* — to respect the time-series caveat).
    """

    alpha: float = 0.1
    normalized: bool = True
    q: float = 1.0

    def fit(self, mu: np.ndarray, y: np.ndarray, sigma: Optional[np.ndarray] = None) -> "Conformal":
        mu = np.asarray(mu, dtype=float)
        y = np.asarray(y, dtype=float)
        res = np.abs(y - mu)
        if self.normalized and sigma is not None:
            s = np.maximum(np.asarray(sigma, dtype=float), 1e-3)
            score = res / s
        else:
            self.normalized = False
            score = res
        n = score.size
        # Finite-sample conformal level.
        level = min(1.0, np.ceil((n + 1) * (1 - self.alpha)) / n) if n > 0 else 1.0
        self.q = float(np.quantile(score, level)) if n > 0 else 0.0
        return self

    def interval(self, mu: np.ndarray, sigma: Optional[np.ndarray] = None,
                 nonneg: bool = False) -> Tuple[np.ndarray, np.ndarray]:
        mu = np.asarray(mu, dtype=float)
        if self.normalized and sigma is not None:
            half = self.q * np.maximum(np.asarray(sigma, dtype=float), 1e-3)
        else:
            half = self.q
        lower = mu - half
        upper = mu + half
        if nonneg:
            lower = np.maximum(lower, 0.0)
        return lower, upper


# ──────────────────────────────────────────────────────────────────────────
# Stacking combiner that ties it together
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class StackedEnsemble:
    """Per-variable stacking meta-learner + EMOS + conformal.

    Members are referenced by name; their predictions are supplied as columns of
    a matrix at fit/apply time (the trainer owns producing them). The meta-model
    is a ridge on member predictions; ``spread`` for EMOS is the across-member
    standard deviation augmented with any member-supplied sigma.
    """

    var: str
    member_names: List[str]
    meta: Ridge
    emos: EMOS
    conformal: Conformal
    weights: Dict[str, float] = field(default_factory=dict)  # |meta coef| share

    def blend(self, member_preds: np.ndarray) -> np.ndarray:
        """Meta-learner blended mean from a (N, M) member-prediction matrix."""
        pred = self.meta.predict(member_preds)
        if self.var == "rainfall":
            pred = np.maximum(pred, 0.0)
        return pred


def _member_spread(member_preds: np.ndarray, member_sigma: Optional[np.ndarray]) -> np.ndarray:
    """Combine across-member dispersion with mean member sigma into one spread."""
    disp = member_preds.std(axis=1)
    if member_sigma is not None:
        # Quadrature-combine ensemble dispersion with the mean predictive sigma.
        msig = np.nanmean(member_sigma, axis=1)
        msig = np.where(np.isfinite(msig), msig, 0.0)
        return np.sqrt(disp ** 2 + msig ** 2)
    return disp


def fit_stack(
    var: str,
    member_names: Sequence[str],
    val_preds: np.ndarray,            # (Nval, M) member means on validation
    y_val: np.ndarray,                # (Nval,)
    val_sigma: Optional[np.ndarray] = None,  # (Nval, M) member sigmas (optional)
    alpha: float = 0.1,
    ridge_alpha: float = 1.0,
) -> StackedEnsemble:
    """Fit the stacking ridge, EMOS, and conformal calibrators on validation data."""
    nonneg = var == "rainfall"
    member_names = list(member_names)

    # 1) Stacking ridge on member means.
    meta = Ridge(alpha=ridge_alpha, nonneg=nonneg).fit(val_preds, y_val)
    blended = meta.predict(val_preds)

    # Member importance from standardised ridge weights (share of |w|).
    w = np.abs(meta.w) if meta.w is not None else np.ones(len(member_names))
    wsum = float(w.sum()) if w.sum() > 1e-12 else 1.0
    weights = {member_names[i]: round(float(w[i] / wsum), 4) for i in range(len(member_names))}

    # 2) EMOS on blended mean + member spread.
    spread = _member_spread(val_preds, val_sigma)
    emos = EMOS(nonneg=nonneg).fit(blended, spread, y_val)
    mu_cal, sigma_cal = emos.apply(blended, spread)

    # 3) Conformal on the EMOS-calibrated mean/sigma.
    conf = Conformal(alpha=alpha, normalized=True).fit(mu_cal, y_val, sigma_cal)

    return StackedEnsemble(var=var, member_names=member_names, meta=meta,
                           emos=emos, conformal=conf, weights=weights)


def apply_stack(stack: StackedEnsemble, member_preds: np.ndarray,
                member_sigma: Optional[np.ndarray] = None
                ) -> Dict[str, np.ndarray]:
    """Produce calibrated (mu, sigma, lower, upper) for a member-prediction matrix."""
    nonneg = stack.var == "rainfall"
    blended = stack.meta.predict(member_preds)
    spread = _member_spread(member_preds, member_sigma)
    mu, sigma = stack.emos.apply(blended, spread)
    lower, upper = stack.conformal.interval(mu, sigma, nonneg=nonneg)
    return {"mu": mu, "sigma": sigma, "lower": lower, "upper": upper}


__all__ = [
    "Ridge",
    "EMOS",
    "Conformal",
    "StackedEnsemble",
    "fit_stack",
    "apply_stack",
]
