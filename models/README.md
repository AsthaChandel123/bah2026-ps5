# `models/` — AI Prediction Core (ISRO BAH 2026 · PS5)

The AI/ML ensemble of the **Bharat Climate Twin** (ARCHITECTURE.md §6). It
**trains on data, produces short-term rainfall + temperature forecasts with
uncertainty, and reports honest validation metrics** from a true train / val /
test split — and it is engineered to run **even when no heavy DL library can be
installed** (ARCHITECTURE.md §16, Risk #3).

Pilot = **Marathwada 0.25° grid** (14 lat × 20 lon = **280 cells**, CONTRACT.md).

---

## What this produces

Two serving artifacts (schema-compatible with the frontend `MetricsPanel`), written
to **both** `data/processed/sample/` and `frontend/public/data/` (identical bytes):

| File | What |
|---|---|
| `metrics.json` | Per-model **and** ensemble metrics on the held-out **test years** — RMSE, MAE, bias, correlation; rainfall CSI/POD/FAR at 1/10/50 mm/day; ensemble CRPS + interval coverage; and a **skill score vs the climatology baseline** for every model. |
| `forecast.json` | A **7-day-lead** ensemble forecast of rainfall/tmax/tmin over the grid, with **per-lead uncertainty** that grows with lead time. |

---

## The tiered ensemble (what is implemented)

Members are organised so that **the numpy/stdlib tier always trains** and the
heavier tiers are added only when their library imports. This is the core
robustness guarantee.

| # | Member | File | Needs | Role |
|---|---|---|---|---|
| 1 | **Climatology** (day-of-year mean) | `baselines.py` | numpy | **Skill reference** — every skill score is `1 − RMSE/RMSE_clim`. |
| 1 | **Persistence** (tomorrow = today) | `baselines.py` | numpy | Naive baseline. |
| 1 | **Damped persistence / AR(1)** | `baselines.py` | numpy | Anomaly persistence with fitted lag-1 `phi`. |
| 3 | **Ridge / linear regression** | `ensemble.py` | numpy | A base learner **and** the stacking meta-learner. |
| 6 | **Analog ensemble (K-NN)** | `analog.py` | numpy | K most-similar historical days → forecast **+ spread** (cheap UQ). |
| 2 | **Gradient boosting** | `boosting.py` | xgboost → lightgbm → sklearn HGB/RF | Per-cell next-day prediction from engineered features (one model/variable). |
| 4 | **ConvLSTM** | `deeplearning.py` | torch (optional) | Spatiotemporal rainfall/temperature **field** nowcaster (small, CPU-OK). |
| 5 | **U-Net** | `deeplearning.py` | torch (optional) | Small CNN field predictor / **downscaling** hook. |
| 7 | **Ensemble combiner** | `ensemble.py` | numpy | **Stacking** (ridge on validation member preds) + **EMOS** mean/variance calibration + **conformal** prediction intervals. |

**Feature engineering** (`data.py`, per cell, predicting day *t+1*): lagged
values of all three variables at *t, t-1, t-2*; day-of-year sin/cos harmonics
(annual + semi-annual); 4-neighbour mean of the target; normalised lat/lon;
3- and 7-day rainfall accumulation; and the **train-only** daily climatological
value for the target day.

---

## Honest results

**No leakage:** features use only past lags within a year; the day-of-year
climatology is fit on **train years only**; base members fit on **train**; the
stacking / EMOS / conformal calibrators fit on **validation**; every reported
number is computed on the **untouched test years**. The split is **year-blocked**
(NEVER random k-fold — ARCHITECTURE.md §6.5): with the default 20-year window
(2006–2025), train = 2006–2020, val = 2021–2022, **test = 2023–2025**.

Headline (full run; exact numbers reprinted by the CLI and stored in
`metrics.json` → run `python -m models.train` to regenerate):

* **The fused ensemble beats the climatology baseline on all three variables**
  (positive `skill_vs_clim`), and on **rainfall correlation**.
* **Temperature** — ensemble tmax/tmin RMSE are below climatology RMSE
  (positive skill); the stacking meta-learner puts most weight on the
  ridge + boosting members and ~0 on raw persistence, as expected.
* **Rainfall** — the ensemble improves wet/dry **CSI** over climatology and
  raises the correlation; absolute rainfall RMSE stays high because daily
  rainfall is heavy-tailed and largely stochastic (honest behaviour).
* **Uncertainty is calibrated** — 90 % conformal prediction intervals achieve
  ≈ 0.90 empirical coverage on the test years; ensemble **CRPS** is reported per
  variable and averaged.

> Why the skill margins are modest: the PoC trains on the repo's **synthetic**
> generator (`pipeline.synthetic`), whose daily fields carry a deliberately large
> unpredictable per-cell noise component, so climatology is already near-optimal
> and there is little day-to-day signal to beat it by. The pipeline, metrics, and
> calibration are exactly what you run on **real IMD/IMDAA data**, where the
> learnable signal (and hence the skill margin) is substantially larger.

---

## How to run

```bash
# Always-on core only (no ML libs needed):
pip install numpy

# Full ensemble (CPU is fine):
pip install -r models/requirements.txt
# CPU-only torch if the default wheel is unavailable:
pip install --index-url https://download.pytorch.org/whl/cpu torch

# Train everything available, evaluate on test years, write both artifacts:
python -m models.train            # full ~20-year run
python -m models.train --quick    # smaller window, faster smoke test
python -m models.train --no-torch # skip ConvLSTM/U-Net even if torch is present

# Inspect / regenerate a forecast without re-evaluating:
python -m models.predict --leads 7
```

`models/train.py` auto-detects which libraries are present, logs the chosen
gradient-boosting backend and whether torch is used, lists any members skipped,
and records `libs_used` + `models_skipped` inside `metrics.json`.

---

## Code layout

```
models/
├─ __init__.py        package + overview
├─ data.py            load/generate multi-year data, feature engineering, year-blocked splits
├─ baselines.py       climatology, persistence, damped-persistence/AR(1)
├─ boosting.py        gradient boosting (xgboost→lightgbm→sklearn HGB/RF)
├─ deeplearning.py    torch ConvLSTM + U-Net (import-guarded; skip if no torch)
├─ analog.py          analog ensemble (K-NN historical days → mean + spread)
├─ ensemble.py        Ridge + stacking + EMOS + conformal prediction
├─ evaluate.py        RMSE/MAE/bias/corr, CSI/POD/FAR, CRPS, coverage, skill
├─ train.py           CLI: trains all available members, evaluates, writes artifacts
├─ predict.py         CLI/API: produce a forecast / read published artifacts
├─ requirements.txt   pinned (optional) deps with notes on what is optional
├─ artifacts/         small fitted artifacts (heavy weights git-ignored)
└─ README.md          this file
```

---

## How this extends to the full ARCHITECTURE.md ensemble

This PoC is the **Tier-1** slice of ARCHITECTURE.md §6.2; the same interfaces
extend cleanly to the full national system:

* **Data** — swap `pipeline.synthetic` for the fused **IMD/IMDAA/ERA5/IMERG**
  analysis cube (the data pipeline's output). `data.py`'s feature table and
  year-blocked splits are unchanged; add **leave-one-monsoon-out** and
  **spatially-blocked** folds (§6.5) for nested CV.
* **Members** — promote the small ConvLSTM/U-Net to the full §6.2 nets, add the
  **CorrDiff/diffusion** downscaler for sharp extremes, **SARIMAX** with
  exogenous ENSO/IOD/MJO indices, and **Earth2Studio** FourCastNet/Pangu/GraphCast
  as global large-scale **forcing** (inference-only). Each plugs into the same
  `MemberStore` → stacking flow.
* **Combiner** — the stacking + EMOS + conformal combiner already implements the
  §6.3 consensus engine; add **BMA** and **regime-conditioned weights** (SOM
  synoptic regime as a meta-feature) for state-dependent blending.
* **DA-in-the-loop** — the analysis cube becomes the model background; couple to
  the OI/Kriging-KED fusion (then EnKF→LETKF) so observations correct the state
  each cycle (§6.1, §6.6).
* **Metrics** — `evaluate.py` already covers the §15 deterministic, categorical,
  and probabilistic suites; add **FSS/SSIM** (spatial), **Brier/BSS**, reliability
  diagrams, and **EDI/SEDI** for extremes.
```
