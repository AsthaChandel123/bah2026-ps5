"""
models.predict — inference helpers
=================================
Thin convenience layer over :mod:`models.train` for producing forecasts without
re-running the whole evaluation, and for reading the published artifacts.

The heavy lifting (fitting members + calibrators) lives in ``train.run``; here we
expose:

* :func:`forecast` — train the always-available members on the full dataset and
  return the same 7-day ensemble forecast dict that ``train`` writes (handy for
  notebooks / the backend API), without touching the metrics file.
* :func:`load_metrics` / :func:`load_forecast` — read the committed JSON
  artifacts from ``data/processed/sample/``.

Run
---
    python -m models.predict            # prints a forecast summary
    python -m models.predict --leads 5  # custom lead count
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

import numpy as np

from . import baselines as base_mod
from . import ensemble as ens_mod
from .data import VARS, prepare
from . import train as train_mod

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SAMPLE_DIR = os.path.join(_ROOT, "data", "processed", "sample")


def forecast(n_leads: int = 7, quick: bool = True) -> Dict[str, object]:
    """Train always-available members + calibrators and return a forecast dict.

    Uses ``quick`` by default (recent-years window) so it returns promptly; pass
    ``quick=False`` for the full multi-decade training set.
    """
    if quick:
        from .data import load_dataset
        ds = load_dataset(years=range(2016, 2026), n_test=3, n_val=2)
        prep = prepare(ds)
    else:
        prep = prepare()
        ds = prep.ds

    baselines = base_mod.fit_baselines(ds, prep.clim)

    # Fit the numpy members + per-variable stacking/EMOS/conformal on val rows.
    from . import analog as analog_mod
    store = train_mod.MemberStore()
    stacks: Dict[str, ens_mod.StackedEnsemble] = {}
    for v in VARS:
        tbl = prep.tables[v]
        X, y = tbl["X"], tbl["y"]
        tix, cix = tbl["t"], tbl["c"]
        m_tr, m_va, m_te = tbl["train"], tbl["val"], tbl["test"]
        for bname in ("climatology", "persistence", "damped_persistence"):
            vp = base_mod.predict_table(baselines[bname], ds, v, tix[m_va], cix[m_va])
            tp = base_mod.predict_table(baselines[bname], ds, v, tix[m_te], cix[m_te])
            store.add(v, bname, vp, tp)
        ridge = ens_mod.Ridge(alpha=1.0, nonneg=(v == "rainfall")).fit(X[m_tr], y[m_tr])
        store.add(v, "ridge", ridge.predict(X[m_va]), ridge.predict(X[m_te]),
                  val_sig=np.full(m_va.sum(), ridge.resid_sigma),
                  test_sig=np.full(m_te.sum(), ridge.resid_sigma))
        an = analog_mod.fit(v, ds, k=20)
        vmu, vsg = analog_mod.predict_table(an, ds, tix[m_va], cix[m_va])
        tmu, tsg = analog_mod.predict_table(an, ds, tix[m_te], cix[m_te])
        store.add(v, "analog", vmu, tmu, val_sig=vsg, test_sig=tsg)

        names, val_mat, _, val_sig, _ = store.matrices(v)
        y_val = y[m_va]
        stacks[v] = ens_mod.fit_stack(v, names, val_mat, y_val, val_sigma=val_sig, alpha=0.1)

    return train_mod.build_forecast(ds, prep, baselines, stacks, store,
                                    n_leads=n_leads, quick=quick)


def load_metrics() -> Dict[str, object]:
    with open(os.path.join(_SAMPLE_DIR, "metrics.json")) as f:
        return json.load(f)


def load_forecast() -> Dict[str, object]:
    with open(os.path.join(_SAMPLE_DIR, "forecast.json")) as f:
        return json.load(f)


def _summary(fc: Dict[str, object]) -> str:
    lines = [f"issue_date={fc['issue_date']} leads={fc['leads']}"]
    for v in VARS:
        arr = np.asarray(fc[v])  # (L, nlat, nlon)
        unc = np.asarray(fc["uncertainty"][v])
        lines.append(f"  {v:8s} lead1 mean={arr[0].mean():.2f} "
                     f"lead{len(arr)} mean={arr[-1].mean():.2f} "
                     f"unc lead1={unc[0].mean():.2f}→lead{len(arr)}={unc[-1].mean():.2f}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Produce / inspect a Bharat Climate Twin forecast.")
    ap.add_argument("--leads", type=int, default=7)
    ap.add_argument("--full", action="store_true", help="Use the full multi-decade training window.")
    args = ap.parse_args(argv)
    fc = forecast(n_leads=args.leads, quick=not args.full)
    print(_summary(fc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
