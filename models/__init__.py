"""
models — the AI prediction core of the Bharat Climate Twin (ISRO BAH 2026 PS5)
==============================================================================

A real, runnable, tiered AI ensemble that

1. **trains** on a multi-year daily climate dataset over the Marathwada 0.25°
   pilot grid (14 lat × 20 lon = 280 cells),
2. produces **short-term rainfall + temperature forecasts with uncertainty**, and
3. reports **honest validation metrics** from a true year-blocked train/val/test
   split (no leakage), with skill scored against a daily-climatology baseline.

The implementation is **tiered** so something real always trains regardless of
which heavy libraries are installed (ARCHITECTURE.md §16, Risk #3):

* Baselines (numpy/stdlib, always)   — climatology, persistence, damped-persistence/AR(1).
* Ridge / linear (numpy, always)     — a learner *and* the stacking meta-learner.
* Analog ensemble (numpy, always)    — K-nearest historical-day forecast + spread.
* Gradient boosting (optional)        — XGBoost → LightGBM → sklearn HGB/RF.
* ConvLSTM + U-Net (optional, torch)  — spatiotemporal nowcast / field downscale.
* Ensemble combiner (numpy, always)  — stacking + EMOS calibration + conformal PIs.

See ``models/README.md`` for what was implemented, how to run, and the honest
results, plus how this PoC extends to the full ARCHITECTURE.md §6 ensemble.
"""

from __future__ import annotations

__all__ = [
    "data",
    "baselines",
    "boosting",
    "deeplearning",
    "analog",
    "ensemble",
    "evaluate",
]

__version__ = "1.0"
