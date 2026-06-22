"""
models.train — CLI entry point
==============================
Trains every member the environment supports, evaluates each member AND the
fused ensemble on the **held-out test years**, and writes the two serving
artifacts (replacing the stub):

* ``data/processed/sample/metrics.json``  — honest validation metrics.
* ``data/processed/sample/forecast.json`` — a 7-day-lead ensemble forecast with
  per-lead uncertainty over the pilot grid.

Both files are mirrored byte-identically into ``frontend/public/data/``.

Run
---
    python -m models.train            # full run (≈20 years, all members)
    python -m models.train --quick    # smaller window for a fast smoke test

The pipeline is leakage-free: features use only past lags within a year, the
day-of-year climatology is fit on **train years only**, base members are fit on
train, the stacking/EMOS/conformal calibrators are fit on **validation**, and
every number reported in ``metrics.json`` comes from the untouched **test**
years. Skill scores are ``1 − RMSE_model / RMSE_climatology``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import shutil
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from . import analog as analog_mod
from . import baselines as base_mod
from . import boosting as boost_mod
from . import deeplearning as dl_mod
from . import ensemble as ens_mod
from . import evaluate as ev
from .data import VARS, GRID, ClimateDataset, PreparedData, doy_of, prepare

# Repo-root-relative artifact paths.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SAMPLE_DIR = os.path.join(_ROOT, "data", "processed", "sample")
_FRONTEND_DIR = os.path.join(_ROOT, "frontend", "public", "data")
_ARTIFACT_DIR = os.path.join(_HERE, "artifacts")


def _log(msg: str) -> None:
    print(f"[train] {msg}", flush=True)


# ──────────────────────────────────────────────────────────────────────────
# Member registry — produces (val_preds, test_preds, sigma) per member/var
# ──────────────────────────────────────────────────────────────────────────
class MemberStore:
    """Holds per-variable member predictions on val/test rows + sigma columns."""

    def __init__(self):
        # var -> {"names": [...], "val": (Nval,M), "test": (Ntest,M),
        #          "val_sig": (Nval,M) or None, "test_sig": ...}
        self.data: Dict[str, Dict[str, object]] = {}

    def add(self, var: str, name: str, val_pred: np.ndarray, test_pred: np.ndarray,
            val_sig: Optional[np.ndarray] = None, test_sig: Optional[np.ndarray] = None):
        d = self.data.setdefault(var, {"names": [], "val": [], "test": [],
                                       "val_sig": [], "test_sig": []})
        d["names"].append(name)          # type: ignore[union-attr]
        d["val"].append(val_pred)         # type: ignore[union-attr]
        d["test"].append(test_pred)       # type: ignore[union-attr]
        n_val, n_test = val_pred.shape[0], test_pred.shape[0]
        d["val_sig"].append(val_sig if val_sig is not None else np.full(n_val, np.nan))   # type: ignore[union-attr]
        d["test_sig"].append(test_sig if test_sig is not None else np.full(n_test, np.nan))  # type: ignore[union-attr]

    def matrices(self, var: str):
        d = self.data[var]
        names = list(d["names"])                       # type: ignore[arg-type]
        val = np.stack(d["val"], axis=1)               # type: ignore[arg-type]
        test = np.stack(d["test"], axis=1)             # type: ignore[arg-type]
        val_sig = np.stack(d["val_sig"], axis=1)       # type: ignore[arg-type]
        test_sig = np.stack(d["test_sig"], axis=1)     # type: ignore[arg-type]
        return names, val, test, val_sig, test_sig


# ──────────────────────────────────────────────────────────────────────────
# Training / evaluation
# ──────────────────────────────────────────────────────────────────────────
def run(quick: bool = False, with_torch: bool = True) -> Dict[str, object]:
    t_start = time.time()
    libs_used: List[str] = ["numpy", f"scipy?"]
    libs_used = ["numpy"]

    # --- data ---
    if quick:
        from .data import load_dataset
        ds = load_dataset(years=range(2016, 2026), n_test=3, n_val=2)
        prep = prepare(ds)
    else:
        prep = prepare()  # default 2006..2025
        ds = prep.ds
    _log(f"dataset T={ds.T} | train={ds.train_years} val={ds.val_years} test={ds.test_years}")

    test_period = f"{ds.test_years[0]}–{ds.test_years[-1]}"

    # --- fit baselines (train-only climatology already in prep.clim) ---
    baselines = base_mod.fit_baselines(ds, prep.clim)
    _log("baselines fitted: climatology, persistence, damped_persistence")

    # --- boosting backend / torch availability ---
    boost_backend = boost_mod.backend_name()
    torch_ok = dl_mod.available() and with_torch
    if boost_backend != "none":
        libs_used.append(boost_backend)
    if torch_ok:
        libs_used.append("torch")
    _log(f"boosting backend = {boost_backend} | torch = {torch_ok}")

    skipped: List[str] = []
    store = MemberStore()

    # Per-variable model metrics accumulator for metrics.json "models" list.
    model_rows: List[Dict[str, object]] = []
    baseline_metrics: Dict[str, Dict[str, object]] = {}
    clim_rmse: Dict[str, float] = {}

    # Pre-train torch field models once per variable (cubes reused).
    torch_models: Dict[str, Dict[str, object]] = {v: {} for v in VARS}
    if torch_ok:
        for v in VARS:
            for kind in ("convlstm", "unet"):
                _log(f"training torch {kind} for {v} ...")
                tm = dl_mod.fit(v, ds, kind=kind,
                                epochs=4 if quick else 8,
                                hid=10 if quick else 12)
                if tm is not None:
                    torch_models[v][kind] = tm
    else:
        skipped += ["ConvLSTM (torch unavailable)", "U-Net (torch unavailable)"]

    for v in VARS:
        tbl = prep.tables[v]
        X, y = tbl["X"], tbl["y"]
        tix, cix = tbl["t"], tbl["c"]
        m_tr, m_va, m_te = tbl["train"], tbl["val"], tbl["test"]
        # Target day index = source day + 1 (for torch cube lookups).
        tgt_t = tix + 1

        y_val, y_test = y[m_va], y[m_te]

        # ----- Baselines (climatology / persistence / damped) -----
        for bname in ("climatology", "persistence", "damped_persistence"):
            val_p = base_mod.predict_table(baselines[bname], ds, v, tix[m_va], cix[m_va])
            test_p = base_mod.predict_table(baselines[bname], ds, v, tix[m_te], cix[m_te])
            store.add(v, bname, val_p, test_p)
            met = ev.deterministic_metrics(test_p, y_test, v)
            if bname == "climatology":
                clim_rmse[v] = met["RMSE"]  # type: ignore[assignment]
            if bname in ("climatology", "persistence"):
                baseline_metrics.setdefault(bname, {})[v] = met

        # ----- Ridge linear learner (numpy, always) -----
        ridge = ens_mod.Ridge(alpha=1.0, nonneg=(v == "rainfall")).fit(X[m_tr], y[m_tr])
        store.add(v, "ridge", ridge.predict(X[m_va]), ridge.predict(X[m_te]),
                  val_sig=np.full(m_va.sum(), ridge.resid_sigma),
                  test_sig=np.full(m_te.sum(), ridge.resid_sigma))

        # ----- Analog ensemble (numpy, always) -----
        an = analog_mod.fit(v, ds, k=20 if quick else 25)
        an_val_mu, an_val_sg = analog_mod.predict_table(an, ds, tix[m_va], cix[m_va])
        an_te_mu, an_te_sg = analog_mod.predict_table(an, ds, tix[m_te], cix[m_te])
        store.add(v, "analog", an_val_mu, an_te_mu, val_sig=an_val_sg, test_sig=an_te_sg)

        # ----- Boosting (optional) -----
        if boost_backend != "none":
            bm = boost_mod.fit(v, X[m_tr], y[m_tr], X[m_va], y_val,
                               feature_names=prep.spec[v].names,
                               max_train=120_000 if quick else 250_000)
            if bm is not None:
                store.add(v, "boosting", bm.predict(X[m_va]), bm.predict(X[m_te]),
                          val_sig=np.full(m_va.sum(), bm.resid_sigma),
                          test_sig=np.full(m_te.sum(), bm.resid_sigma))

        # ----- Torch field members (optional) -----
        for kind, label in (("convlstm", "convlstm"), ("unet", "unet")):
            tm = torch_models[v].get(kind)
            if tm is not None:
                val_p = dl_mod.predict_table(tm, ds, tgt_t[m_va], cix[m_va])
                test_p = dl_mod.predict_table(tm, ds, tgt_t[m_te], cix[m_te])
                # Some early-year targets may be NaN (no window) → fill w/ climatology.
                clim_val = base_mod.predict_table(baselines["climatology"], ds, v, tix[m_va], cix[m_va])
                clim_te = base_mod.predict_table(baselines["climatology"], ds, v, tix[m_te], cix[m_te])
                val_p = np.where(np.isfinite(val_p), val_p, clim_val)
                test_p = np.where(np.isfinite(test_p), test_p, clim_te)
                store.add(v, label, val_p, test_p,
                          val_sig=np.full(m_va.sum(), tm.resid_sigma),
                          test_sig=np.full(m_te.sum(), tm.resid_sigma))

        _log(f"[{v}] members: {store.data[v]['names']}")

        # ----- Per-member metrics on TEST -----
        names, _, test_mat, _, _ = store.matrices(v)
        for j, nm in enumerate(names):
            met = ev.deterministic_metrics(test_mat[:, j], y_test, v)
            met["skill_vs_clim"] = round(ev.skill_score(met["RMSE"], clim_rmse[v]), 4)  # type: ignore[arg-type]
            model_rows.append({
                "name": nm, "var": v,
                "RMSE": met["RMSE"], "MAE": met["MAE"],
                "CSI": met["CSI"], "bias": met["bias"],
                "corr": met["corr"], "skill_vs_clim": met["skill_vs_clim"],
                "categorical": met.get("categorical"),
            })

    # ----- Fit + evaluate the fused ensemble per variable -----
    ensemble_block: Dict[str, object] = {"method": "stacking(ridge)+EMOS+conformal"}
    crps_list: List[float] = []
    cov_list: List[float] = []
    stacks: Dict[str, ens_mod.StackedEnsemble] = {}
    for v in VARS:
        names, val_mat, test_mat, val_sig, test_sig = store.matrices(v)
        tbl = prep.tables[v]
        y_val = tbl["y"][tbl["val"]]
        y_test = tbl["y"][tbl["test"]]

        stack = ens_mod.fit_stack(v, names, val_mat, y_val, val_sigma=val_sig, alpha=0.1)
        stacks[v] = stack
        out = ens_mod.apply_stack(stack, test_mat, test_sig)
        mu, sigma = out["mu"], out["sigma"]
        lower, upper = out["lower"], out["upper"]

        det = ev.deterministic_metrics(mu, y_test, v)
        crps = ev.crps_gaussian(mu, sigma, y_test)
        cov = ev.interval_coverage(lower, upper, y_test)
        skill = ev.skill_score(det["RMSE"], clim_rmse[v])  # type: ignore[arg-type]
        crps_list.append(crps)
        cov_list.append(cov["coverage"])

        block: Dict[str, object] = {
            "RMSE": det["RMSE"], "MAE": det["MAE"], "bias": det["bias"],
            "corr": det["corr"], "R2": det["R2"], "CSI": det["CSI"],
            "CRPS": round(crps, 4), "skill_vs_clim": round(skill, 4),
            "coverage_90": round(cov["coverage"], 4),
            "interval_width": round(cov["width"], 4),
            "weights": stack.weights,
        }
        if v == "rainfall":
            block["categorical"] = det.get("categorical")
        ensemble_block[v] = block
        _log(f"[ensemble {v}] RMSE={det['RMSE']} MAE={det['MAE']} "
             f"skill_vs_clim={skill:.3f} CRPS={crps:.3f} cov90={cov['coverage']:.3f}")

    ensemble_block["CRPS"] = round(float(np.nanmean(crps_list)), 4)
    ensemble_block["coverage"] = round(float(np.nanmean(cov_list)), 4)

    # ----- Assemble metrics.json -----
    members_present = store.data[VARS[0]]["names"]
    note = (
        f"Tiered AI ensemble trained on {len(ds.years)} yr synthetic Marathwada "
        f"0.25° data (14×20=280 cells); year-blocked split, test years held out "
        f"({test_period}); leakage-free (train-only climatology, val-fit "
        f"stacking/EMOS/conformal). Members: {', '.join(members_present)}. "
        f"Skill = 1 − RMSE/clim. Lower RMSE/MAE/CRPS better; higher CSI better."
    )
    metrics = {
        "models": model_rows,
        "ensemble": ensemble_block,
        "baselines": baseline_metrics,
        "test_period": test_period,
        "train_period": f"{ds.train_years[0]}–{ds.train_years[-1]}",
        "val_period": f"{ds.val_years[0]}–{ds.val_years[-1]}",
        "rain_thresholds_mm": list(ev.RAIN_THRESHOLDS),
        "note": note,
        "generated": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "libs_used": libs_used,
        "models_skipped": skipped,
        "grid": {"nlat": ds.grid.nlat, "nlon": ds.grid.nlon,
                 "bbox": list(ds.grid.bbox), "res_deg": ds.grid.res_deg},
    }

    # ----- Build the 7-day forecast.json from the best ensemble -----
    forecast = build_forecast(ds, prep, baselines, stacks, store, quick=quick)

    _write_artifacts(metrics, forecast)
    _log(f"DONE in {time.time() - t_start:.1f}s")
    return {"metrics": metrics, "forecast_meta": {
        "leads": forecast["leads"], "issue_date": forecast["issue_date"]}}


# ──────────────────────────────────────────────────────────────────────────
# 7-day recursive ensemble forecast (for forecast.json)
# ──────────────────────────────────────────────────────────────────────────
def build_forecast(ds: ClimateDataset, prep: PreparedData,
                   baselines: Dict[str, object], stacks: Dict[str, ens_mod.StackedEnsemble],
                   store: MemberStore, n_leads: int = 7, quick: bool = False) -> Dict[str, object]:
    """Produce a 7-day-lead forecast field + per-lead uncertainty.

    Strategy (robust + honest): the ensemble is a next-day (lead-1) system, so
    we roll it forward recursively. For tractability and stability the forecast
    members are the **always-available** numpy members (damped-persistence,
    ridge, analog) plus climatology, blended by each variable's fitted stacking
    meta-learner and calibrated by its EMOS+conformal. Uncertainty per lead is
    the EMOS sigma inflated by ``sqrt(lead)`` (error growth with lead time) and
    reported as the conformal half-width — a calibrated, monotonically growing
    band. The issue day is the last day of the dataset.
    """
    nlat, nlon = ds.grid.shape
    issue_t = ds.T - 1
    issue_date = ds.dates[issue_t]

    # Working copies of the state we roll forward (append predicted days).
    state = {v: [ds.cube(v)[t].copy() for t in range(ds.T)] for v in VARS}
    dates_axis = list(ds.dates)
    year_axis = list(ds.year_of_day)

    # Build a per-lead set of fields.
    out_fields = {v: [] for v in VARS}
    out_unc = {v: [] for v in VARS}
    lead_dates: List[str] = []

    # Helper: build the member-prediction matrix for a single forecast day,
    # using the same member set/order the stack was trained on, restricted to
    # members we can evaluate recursively (numpy ones). Missing members are
    # imputed with the climatology column so the meta-learner sees full width.
    clim_b = baselines["climatology"]
    pers_b = baselines["persistence"]
    damp_b = baselines["damped_persistence"]
    an_models = {v: analog_mod.fit(v, ds, k=20 if quick else 25) for v in VARS}
    ridge_models: Dict[str, ens_mod.Ridge] = {}
    for v in VARS:
        tbl = prep.tables[v]
        ridge_models[v] = ens_mod.Ridge(alpha=1.0, nonneg=(v == "rainfall")).fit(
            tbl["X"][tbl["train"]], tbl["y"][tbl["train"]])

    # A tiny dataset-like shim so baseline/analog .predict_next can read the
    # growing state. We extend ds in place via a lightweight wrapper.
    class _RollDS:
        def __init__(self):
            self.grid = ds.grid
            self.years = ds.years
            self.train_years = ds.train_years
            self.val_years = ds.val_years
            self.test_years = ds.test_years
        @property
        def dates(self):
            return dates_axis
        @property
        def year_of_day(self):
            return np.asarray(year_axis)
        @property
        def T(self):
            return len(dates_axis)
        def cube(self, var):
            return np.stack(state[var], axis=0)

    roll = _RollDS()

    for lead in range(1, n_leads + 1):
        t = len(dates_axis) - 1  # current last day (source for next-day pred)
        # Next-day climatology / persistence / damped fields.
        next_fields: Dict[str, np.ndarray] = {}
        next_unc: Dict[str, np.ndarray] = {}
        for v in VARS:
            stack = stacks[v]
            # Build feature matrix for ALL cells for this single source day t.
            X_day = _features_one_day(roll, prep, v, t)
            ridge_pred = ridge_models[v].predict(X_day)
            an_mu, an_sg = an_models[v].predict_day(roll, t)
            member_cols: Dict[str, np.ndarray] = {
                "climatology": clim_b.predict_next(roll, v, t).reshape(-1),
                "persistence": pers_b.predict_next(roll, v, t).reshape(-1),
                "damped_persistence": damp_b.predict_next(roll, v, t).reshape(-1),
                "ridge": ridge_pred,
                "analog": an_mu.reshape(-1),
            }
            # Assemble matrix in the stack's member order; impute unknown members.
            cols = []
            sig_cols = []
            for nm in stack.member_names:
                if nm in member_cols:
                    cols.append(member_cols[nm])
                else:
                    cols.append(member_cols["climatology"])  # impute
                if nm == "analog":
                    sig_cols.append(an_sg.reshape(-1))
                elif nm == "ridge":
                    sig_cols.append(np.full(nlat * nlon, ridge_models[v].resid_sigma))
                else:
                    sig_cols.append(np.full(nlat * nlon, np.nan))
            M = np.stack(cols, axis=1)
            Msig = np.stack(sig_cols, axis=1)
            out = ens_mod.apply_stack(stack, M, Msig)
            mu = out["mu"].reshape(nlat, nlon)
            sigma = out["sigma"].reshape(nlat, nlon)
            # Inflate uncertainty with lead time (error growth) and report the
            # conformal-scaled half-width as the per-lead uncertainty band.
            half = stack.conformal.q * np.maximum(sigma, 1e-3) * math.sqrt(lead)
            if v == "rainfall":
                mu = np.maximum(mu, 0.0)
            next_fields[v] = mu
            next_unc[v] = half

        # Append the predicted day to the rolling state and advance the axes.
        from datetime import date, timedelta
        last = dates_axis[-1]
        yy, mm, dd = (int(x) for x in last.split("-"))
        nd = (date(yy, mm, dd) + timedelta(days=1))
        dates_axis.append(nd.isoformat())
        year_axis.append(nd.year)
        for v in VARS:
            state[v].append(next_fields[v])
            out_fields[v].append(np.round(next_fields[v], 1).tolist())
            out_unc[v].append(np.round(next_unc[v], 1).tolist())
        lead_dates.append(nd.isoformat())

    return {
        "issue_date": issue_date,
        "leads": list(range(1, n_leads + 1)),
        "dates": lead_dates,
        "lats": [round(x, 4) for x in ds.grid.lats],
        "lons": [round(x, 4) for x in ds.grid.lons],
        "rainfall": out_fields["rainfall"],
        "tmax": out_fields["tmax"],
        "tmin": out_fields["tmin"],
        "uncertainty": {
            "rainfall": out_unc["rainfall"],
            "tmax": out_unc["tmax"],
            "tmin": out_unc["tmin"],
        },
        "units": {"rainfall": "mm/day", "tmax": "°C", "tmin": "°C"},
        "model": "ensemble",
        "method": "stacking(ridge)+EMOS+conformal, recursive multi-lead",
        "generated": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }


def _features_one_day(roll, prep: PreparedData, var: str, t: int) -> np.ndarray:
    """Recompute the engineered feature row for every cell on source day ``t``.

    Mirrors ``data.build_feature_table`` for a single day so the rolling
    forecast feeds the ridge member exactly the features it was trained on.
    """
    from .data import N_LAGS, doy_of as _doy
    grid = roll.grid
    nlat, nlon = grid.nlat, grid.nlon
    ncell = nlat * nlon
    cubes = {v: roll.cube(v) for v in VARS}
    lat_arr = np.asarray(grid.lats)[:, None]
    lon_arr = np.asarray(grid.lons)[None, :]
    lat_norm = (lat_arr - lat_arr.min()) / max(1e-9, (lat_arr.max() - lat_arr.min()))
    lon_norm = (lon_arr - lon_arr.min()) / max(1e-9, (lon_arr.max() - lon_arr.min()))
    lat_flat = np.broadcast_to(lat_norm, (nlat, nlon)).reshape(-1)
    lon_flat = np.broadcast_to(lon_norm, (nlat, nlon)).reshape(-1)

    feat_planes: List[np.ndarray] = []
    for lag in range(N_LAGS):
        tt = max(0, t - lag)
        for v in VARS:
            feat_planes.append(cubes[v][tt].reshape(-1))
    tgt_doy = _doy(roll, t + 1) if (t + 1) < roll.T else (_doy(roll, t) % 366) + 1
    ang = 2 * math.pi * (tgt_doy / 366.0)
    harm = [math.sin(ang), math.cos(ang), math.sin(2 * ang), math.cos(2 * ang)]
    harm_planes = [np.full(ncell, h) for h in harm]

    f = cubes[var][t]
    up = np.empty_like(f); up[1:] = f[:-1]; up[0] = f[0]
    dn = np.empty_like(f); dn[:-1] = f[1:]; dn[-1] = f[-1]
    lf = np.empty_like(f); lf[:, 1:] = f[:, :-1]; lf[:, 0] = f[:, 0]
    rt = np.empty_like(f); rt[:, :-1] = f[:, 1:]; rt[:, -1] = f[:, -1]
    nbr = ((up + dn + lf + rt) / 4.0).reshape(-1)

    rain = cubes["rainfall"]
    acc3 = rain[max(0, t - 2): t + 1].sum(axis=0).reshape(-1)
    acc7 = rain[max(0, t - 6): t + 1].sum(axis=0).reshape(-1)
    clim_next = prep.clim[var][tgt_doy - 1].reshape(-1)

    cols = feat_planes + harm_planes + [nbr, lat_flat, lon_flat, acc3, acc7, clim_next]
    return np.stack(cols, axis=1)


# ──────────────────────────────────────────────────────────────────────────
# Artifact writing + mirroring
# ──────────────────────────────────────────────────────────────────────────
def _write_artifacts(metrics: Dict[str, object], forecast: Dict[str, object]) -> None:
    os.makedirs(_SAMPLE_DIR, exist_ok=True)
    os.makedirs(_FRONTEND_DIR, exist_ok=True)
    os.makedirs(_ARTIFACT_DIR, exist_ok=True)

    for name, obj in (("metrics.json", metrics), ("forecast.json", forecast)):
        path = os.path.join(_SAMPLE_DIR, name)
        with open(path, "w") as f:
            json.dump(obj, f, separators=(",", ":"), allow_nan=False)
        size = os.path.getsize(path)
        # Mirror byte-identically.
        mirror = os.path.join(_FRONTEND_DIR, name)
        shutil.copyfile(path, mirror)
        _log(f"wrote {path} ({size/1024:.1f} KB) and mirrored → {mirror}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Train the Bharat Climate Twin AI ensemble.")
    ap.add_argument("--quick", action="store_true",
                    help="Smaller year window + lighter training for a fast smoke test.")
    ap.add_argument("--no-torch", action="store_true",
                    help="Skip the torch ConvLSTM/U-Net members even if torch is installed.")
    args = ap.parse_args(argv)
    try:
        run(quick=args.quick, with_torch=not args.no_torch)
    except Exception as e:  # pragma: no cover
        _log(f"ERROR: {type(e).__name__}: {e}")
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
