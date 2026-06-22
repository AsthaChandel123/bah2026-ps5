"""
models.boosting
==============
Gradient-boosted-tree learners for per-cell next-day prediction
(ARCHITECTURE.md §6.2 model #36/#37; research/03 §5).

Tiering (graceful degradation — Risk #3)
----------------------------------------
We try gradient-boosting backends in priority order and use the first that
imports:

1. **XGBoost** (`xgboost.XGBRegressor`)            — preferred.
2. **LightGBM** (`lightgbm.LGBMRegressor`)          — fast alt.
3. **sklearn HistGradientBoostingRegressor**        — stdlib-of-the-ML-world.
4. **sklearn RandomForestRegressor**                — final tree fallback.

If *no* tree backend is importable the model marks itself unavailable and the
ensemble simply proceeds without it (the numpy baselines + ridge + analog still
train). One model is trained **per variable**.

Rainfall predictions are clamped to ``>= 0``. We also fit a fast per-variable
residual-spread estimate (std of validation residuals) so the boosting member
can contribute a Gaussian predictive sigma to the ensemble + CRPS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---- Detect the best available boosting backend ---------------------------
_BACKEND: Optional[str] = None
_make_regressor = None


def _detect_backend():
    global _BACKEND, _make_regressor
    if _BACKEND is not None:
        return
    # 1) XGBoost
    try:
        import xgboost as xgb  # type: ignore

        def _mk(**kw):
            return xgb.XGBRegressor(
                n_estimators=kw.get("n_estimators", 300),
                max_depth=kw.get("max_depth", 6),
                learning_rate=kw.get("learning_rate", 0.05),
                subsample=0.8,
                colsample_bytree=0.8,
                reg_lambda=1.0,
                n_jobs=kw.get("n_jobs", 0),
                tree_method="hist",
                objective="reg:squarederror",
                random_state=0,
            )

        _BACKEND, _make_regressor = "xgboost", _mk
        return
    except Exception:
        pass
    # 2) LightGBM
    try:
        import lightgbm as lgb  # type: ignore

        def _mk(**kw):
            return lgb.LGBMRegressor(
                n_estimators=kw.get("n_estimators", 400),
                max_depth=kw.get("max_depth", -1),
                num_leaves=kw.get("num_leaves", 63),
                learning_rate=kw.get("learning_rate", 0.05),
                subsample=0.8,
                colsample_bytree=0.8,
                n_jobs=kw.get("n_jobs", -1),
                random_state=0,
                verbosity=-1,
            )

        _BACKEND, _make_regressor = "lightgbm", _mk
        return
    except Exception:
        pass
    # 3) sklearn HistGradientBoosting
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor  # type: ignore

        def _mk(**kw):
            return HistGradientBoostingRegressor(
                max_iter=kw.get("n_estimators", 300),
                max_depth=kw.get("max_depth", None),
                learning_rate=kw.get("learning_rate", 0.06),
                l2_regularization=1.0,
                random_state=0,
            )

        _BACKEND, _make_regressor = "sklearn_hgb", _mk
        return
    except Exception:
        pass
    # 4) sklearn RandomForest
    try:
        from sklearn.ensemble import RandomForestRegressor  # type: ignore

        def _mk(**kw):
            return RandomForestRegressor(
                n_estimators=kw.get("n_estimators", 200),
                max_depth=kw.get("max_depth", None),
                n_jobs=-1,
                random_state=0,
            )

        _BACKEND, _make_regressor = "sklearn_rf", _mk
        return
    except Exception:
        pass
    _BACKEND, _make_regressor = "none", None


def backend_name() -> str:
    _detect_backend()
    return _BACKEND or "none"


def available() -> bool:
    return backend_name() != "none"


@dataclass
class BoostingModel:
    """One fitted boosting regressor for a single variable."""

    var: str
    backend: str
    model: object
    resid_sigma: float = 1.0  # validation residual std (Gaussian spread)
    feature_names: List[str] = field(default_factory=list)

    def predict(self, X: np.ndarray) -> np.ndarray:
        pred = np.asarray(self.model.predict(X), dtype=float)
        if self.var == "rainfall":
            pred = np.maximum(pred, 0.0)
        return pred


def fit(var: str, X_train: np.ndarray, y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None, y_val: Optional[np.ndarray] = None,
        feature_names: Optional[List[str]] = None,
        max_train: int = 250_000, **kw) -> Optional[BoostingModel]:
    """Fit a boosting model for ``var``. Returns None if no backend is available.

    ``max_train`` subsamples very large feature tables (kept reproducible with a
    fixed seed) so training stays fast on CPU without materially hurting skill.
    """
    _detect_backend()
    if not available():
        return None
    Xtr, ytr = X_train, y_train
    if Xtr.shape[0] > max_train:
        rng = np.random.default_rng(0)
        sel = rng.choice(Xtr.shape[0], size=max_train, replace=False)
        Xtr, ytr = Xtr[sel], ytr[sel]
    reg = _make_regressor(**kw)
    reg.fit(Xtr, ytr)
    model = BoostingModel(var=var, backend=_BACKEND or "none", model=reg,
                          feature_names=list(feature_names or []))
    # Residual spread from validation (fallback to train) for Gaussian sigma.
    if X_val is not None and y_val is not None and X_val.shape[0] > 0:
        resid = y_val - model.predict(X_val)
    else:
        resid = ytr - model.predict(Xtr)
    model.resid_sigma = float(np.std(resid)) if resid.size else 1.0
    return model


__all__ = ["BoostingModel", "fit", "available", "backend_name"]
