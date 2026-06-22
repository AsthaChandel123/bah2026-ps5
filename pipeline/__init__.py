"""
Bharat Climate Twin — data pipeline
===================================
A runnable, multi-source climate-data pipeline for the AI-Powered Digital Twin
of India's Climate (ISRO BAH 2026, Problem Statement 5).

Two paths, by design (ARCHITECTURE.md §4, Risk #8 demo reliability):

1. **Real ingestion** (``pipeline.ingest.*``) — working clients for IMD,
   IMERG, ERA5-Land, MODIS LST, INSAT (MOSDAC), CHIRPS, etc. Each guards its
   imports so a missing library / credential / network never crashes the run.

2. **Synthetic fallback** (``pipeline.synthetic``) — a physically-plausible
   generator that runs on the **Python standard library alone**, so the offline
   demo always has data + precomputed serving artifacts with zero network.

The orchestrator (``pipeline.run_pipeline``) tries (1) per source and falls
back to (2), then harmonizes, fuses (quantile-mapping + OI + triple
collocation), and exports the JSON serving artifacts defined in CONTRACT.md.
"""

from __future__ import annotations

__version__ = "1.0.0"
