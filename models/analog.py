"""
models.analog
============
Analog Ensemble (AnEn) — research/03 method #43, ARCHITECTURE.md §6.2.

Idea
----
For a target day we look up the **K most similar historical days** (the
"analogs") in a training archive and use *their next-day observations* as an
ensemble. The ensemble **mean** is the forecast and the ensemble **standard
deviation** is a cheap, flow-dependent **uncertainty** estimate — exactly the
property the twin needs ("a twin without uncertainty is just a map", P4).

Implementation (pure numpy, always runs)
-----------------------------------------
* The analog "state" for a cell on day ``t`` is a small predictor vector:
  the cell's current value of all three variables, its day-of-year harmonics,
  and its 4-neighbour mean of the target variable — i.e. a compact slice of the
  same features used by the boosting member, so analogs are physically alike.
* Similarity = Euclidean distance in z-scored predictor space.
* The archive is the **training years only** (no leakage). Each archive entry
  stores the predictor vector at day ``t`` and the verifying observation at
  ``t+1`` for that cell.
* Distances are computed **per cell** (each cell has its own archive), which is
  both physically sensible (local climate) and keeps each search tiny
  (≈ train_days entries), so the whole thing is fast without any ML library.

Because a per-cell brute-force K-NN over the test set can be done with a single
vectorised distance matrix per cell, this is comfortably fast for the 280-cell
pilot and ~7 training years.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from .data import VARS, ClimateDataset, doy_of


@dataclass
class AnalogEnsemble:
    """Per-cell analog archives for one variable."""

    var: str
    k: int
    # Per cell: (n_archive, n_pred) predictors and (n_archive,) next-day obs.
    pred_archive: List[np.ndarray]
    obs_archive: List[np.ndarray]
    mu: np.ndarray   # (n_pred,) predictor mean for z-scoring
    sd: np.ndarray   # (n_pred,) predictor std

    def _predictors_for_day(self, ds: ClimateDataset, t: int) -> np.ndarray:
        """Build the (ncell, n_pred) predictor matrix for source day ``t``."""
        nlat, nlon = ds.grid.shape
        ncell = nlat * nlon
        cols: List[np.ndarray] = []
        for v in VARS:
            cols.append(ds.cube(v)[t].reshape(-1))
        ang = 2 * math.pi * (doy_of(ds, t) / 366.0)
        for h in (math.sin(ang), math.cos(ang)):
            cols.append(np.full(ncell, h))
        # 4-neighbour mean of the target var.
        f = ds.cube(self.var)[t]
        up = np.empty_like(f); up[1:] = f[:-1]; up[0] = f[0]
        dn = np.empty_like(f); dn[:-1] = f[1:]; dn[-1] = f[-1]
        lf = np.empty_like(f); lf[:, 1:] = f[:, :-1]; lf[:, 0] = f[:, 0]
        rt = np.empty_like(f); rt[:, :-1] = f[:, 1:]; rt[:, -1] = f[:, -1]
        cols.append(((up + dn + lf + rt) / 4.0).reshape(-1))
        return np.stack(cols, axis=1)  # (ncell, n_pred)

    def predict_day(self, ds: ClimateDataset, t: int) -> Tuple[np.ndarray, np.ndarray]:
        """Return (mean_field, sigma_field) for the t+1 forecast, shape (nlat,nlon)."""
        nlat, nlon = ds.grid.shape
        ncell = nlat * nlon
        P = self._predictors_for_day(ds, t)            # (ncell, n_pred)
        Pz = (P - self.mu) / self.sd
        mean_out = np.empty(ncell)
        sig_out = np.empty(ncell)
        for c in range(ncell):
            arch = self.pred_archive[c]                # (n_arch, n_pred)
            obs = self.obs_archive[c]                  # (n_arch,)
            if arch.shape[0] == 0:
                mean_out[c] = np.nan; sig_out[c] = np.nan
                continue
            d = arch - Pz[c]
            dist = np.einsum("ij,ij->i", d, d)         # squared Euclidean
            k = min(self.k, arch.shape[0])
            idx = np.argpartition(dist, k - 1)[:k]
            members = obs[idx]
            mean_out[c] = float(np.mean(members))
            sig_out[c] = float(np.std(members)) if k > 1 else 0.0
        mean_field = mean_out.reshape(nlat, nlon)
        sig_field = sig_out.reshape(nlat, nlon)
        if self.var == "rainfall":
            mean_field = np.maximum(mean_field, 0.0)
        # Floor sigma so CRPS / intervals are finite.
        sig_field = np.maximum(sig_field, 1e-2)
        return mean_field, sig_field


def fit(var: str, ds: ClimateDataset, k: int = 25) -> AnalogEnsemble:
    """Build per-cell analog archives for ``var`` from the training years."""
    nlat, nlon = ds.grid.shape
    ncell = nlat * nlon

    # Collect (predictor, next-obs) pairs over training years, per source day.
    pred_days: List[np.ndarray] = []   # each (ncell, n_pred)
    obs_days: List[np.ndarray] = []    # each (ncell,)
    # Temporary AnalogEnsemble for predictor construction (mu/sd not yet set).
    tmp = AnalogEnsemble(var=var, k=k, pred_archive=[], obs_archive=[],
                         mu=np.zeros(1), sd=np.ones(1))
    target = ds.cube(var)
    for y in ds.train_years:
        idx = np.where(ds.year_of_day == y)[0]
        t0, t1 = int(idx[0]), int(idx[-1])
        for t in range(t0, t1):  # t+1 must stay within the year
            P = tmp._predictors_for_day(ds, t)         # (ncell, n_pred)
            pred_days.append(P)
            obs_days.append(target[t + 1].reshape(-1))

    pred_all = np.stack(pred_days, axis=0)             # (n_days, ncell, n_pred)
    obs_all = np.stack(obs_days, axis=0)               # (n_days, ncell)
    n_pred = pred_all.shape[2]

    # Global z-scoring stats (over all archive predictors).
    flat = pred_all.reshape(-1, n_pred)
    mu = flat.mean(axis=0)
    sd = flat.std(axis=0)
    sd[sd < 1e-9] = 1.0

    pred_archive: List[np.ndarray] = []
    obs_archive: List[np.ndarray] = []
    for c in range(ncell):
        Pc = (pred_all[:, c, :] - mu) / sd             # (n_days, n_pred)
        pred_archive.append(Pc.astype(np.float32))
        obs_archive.append(obs_all[:, c].astype(np.float32))

    return AnalogEnsemble(var=var, k=k, pred_archive=pred_archive,
                          obs_archive=obs_archive, mu=mu, sd=sd)


def predict_table(model: AnalogEnsemble, ds: ClimateDataset,
                  day_index: np.ndarray, cell_index: np.ndarray
                  ) -> Tuple[np.ndarray, np.ndarray]:
    """Per-sample analog (mean, sigma) matching a feature table's rows."""
    out_mu = np.empty(day_index.shape[0])
    out_sg = np.empty(day_index.shape[0])
    order = np.argsort(day_index)
    di = day_index[order]; ci = cell_index[order]
    uniq, starts = np.unique(di, return_index=True)
    starts = list(starts) + [len(di)]
    for k, t in enumerate(uniq):
        mean_f, sig_f = model.predict_day(ds, int(t))
        mf = mean_f.reshape(-1); sf = sig_f.reshape(-1)
        sl = slice(starts[k], starts[k + 1])
        out_mu[order[sl]] = mf[ci[sl]]
        out_sg[order[sl]] = sf[ci[sl]]
    return out_mu, out_sg


__all__ = ["AnalogEnsemble", "fit", "predict_table"]
