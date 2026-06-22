"""
models.baselines
================
The reference forecasters that define skill (ARCHITECTURE.md §6.5, §15.2).
Everything here is pure numpy / stdlib so the skill reference *always* exists.

Implemented
-----------
* **Climatology** — the train-only day-of-year mean field. The mandated skill
  reference: every other model is scored as ``1 − RMSE_model / RMSE_clim``.
* **Persistence** — tomorrow = today. The naive "no change" forecast.
* **Damped persistence / AR(1)** — tomorrow's anomaly = ``phi`` × today's
  anomaly about climatology, with ``phi`` fitted per variable on the training
  anomalies (the standard lag-1 autocorrelation). Reduces to persistence for
  ``phi=1`` and to climatology for ``phi=0``; the damping is what makes it a
  genuinely better-calibrated baseline than raw persistence.

Each baseline exposes ``predict_next(ds, clim, t)`` returning the full
(nlat, nlon) field forecast for day ``t+1`` given information up to day ``t``,
and a vectorised ``predict_table`` that scores a feature table's samples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from .data import VARS, ClimateDataset, doy_of


@dataclass
class ClimatologyBaseline:
    """Predicts the train-only day-of-year climatological field."""

    clim: Dict[str, np.ndarray]  # var -> (366, nlat, nlon)

    def predict_next(self, ds: ClimateDataset, var: str, t: int) -> np.ndarray:
        tgt_doy = doy_of(ds, t + 1)
        return self.clim[var][tgt_doy - 1]

    def predict_for_targets(self, ds: ClimateDataset, var: str, target_t: np.ndarray) -> np.ndarray:
        """Climatology value at each (target day, cell). target_t are t+1 indices."""
        doys = np.array([doy_of(ds, int(t)) for t in target_t])
        return self.clim[var][doys - 1]  # (N, nlat, nlon)


@dataclass
class PersistenceBaseline:
    """tomorrow == today."""

    def predict_next(self, ds: ClimateDataset, var: str, t: int) -> np.ndarray:
        return ds.cube(var)[t]


@dataclass
class DampedPersistenceBaseline:
    """AR(1) on anomalies about climatology: anom_{t+1} = phi * anom_t.

    ``phi`` is the lag-1 autocorrelation of the training anomaly series, fitted
    per variable in :meth:`fit`.
    """

    clim: Dict[str, np.ndarray]
    phi: Dict[str, float]

    @classmethod
    def fit(cls, ds: ClimateDataset, clim: Dict[str, np.ndarray]) -> "DampedPersistenceBaseline":
        phi: Dict[str, float] = {}
        for v in VARS:
            cube = ds.cube(v)
            # Build anomaly series over training years only, per cell, lag-1 corr.
            num = 0.0
            den = 0.0
            for y in ds.train_years:
                idx = np.where(ds.year_of_day == y)[0]
                t0, t1 = int(idx[0]), int(idx[-1])
                doys = np.array([doy_of(ds, t) for t in range(t0, t1 + 1)])
                anom = cube[t0:t1 + 1] - clim[v][doys - 1]
                a0 = anom[:-1].reshape(-1)
                a1 = anom[1:].reshape(-1)
                num += float(np.sum(a0 * a1))
                den += float(np.sum(a0 * a0))
            phi[v] = max(0.0, min(0.99, num / den)) if den > 1e-9 else 0.0
        return cls(clim=clim, phi=phi)

    def predict_next(self, ds: ClimateDataset, var: str, t: int) -> np.ndarray:
        tgt_doy = doy_of(ds, t + 1)
        cur_doy = doy_of(ds, t)
        clim_next = self.clim[var][tgt_doy - 1]
        anom_today = ds.cube(var)[t] - self.clim[var][cur_doy - 1]
        pred = clim_next + self.phi[var] * anom_today
        if var == "rainfall":
            pred = np.maximum(pred, 0.0)
        return pred


def fit_baselines(ds: ClimateDataset, clim: Dict[str, np.ndarray]) -> Dict[str, object]:
    """Construct all three baselines for a dataset + train-only climatology."""
    return {
        "climatology": ClimatologyBaseline(clim=clim),
        "persistence": PersistenceBaseline(),
        "damped_persistence": DampedPersistenceBaseline.fit(ds, clim),
    }


def predict_table(model: object, ds: ClimateDataset, var: str,
                  day_index: np.ndarray, cell_index: np.ndarray) -> np.ndarray:
    """Vectorised per-sample baseline prediction matching a feature table.

    ``day_index`` holds the source day ``t`` of each sample (target is t+1);
    ``cell_index`` holds the flattened cell id. Returns a (N,) prediction array.
    """
    nlat, nlon = ds.grid.shape
    out = np.empty(day_index.shape[0], dtype=float)
    # Group by unique source day to amortise field computation.
    order = np.argsort(day_index)
    di = day_index[order]
    ci = cell_index[order]
    uniq, starts = np.unique(di, return_index=True)
    starts = list(starts) + [len(di)]
    for k, t in enumerate(uniq):
        field = model.predict_next(ds, var, int(t)).reshape(-1)
        sl = slice(starts[k], starts[k + 1])
        out[order[sl]] = field[ci[sl]]
    return out


__all__ = [
    "ClimatologyBaseline",
    "PersistenceBaseline",
    "DampedPersistenceBaseline",
    "fit_baselines",
    "predict_table",
]
