"""Verbatim artifact endpoints — the exact shapes the frontend already fetches.

``frontend/lib/api.ts`` fetches whole JSON artifacts by filename:
``metadata.json``, ``fields_daily.json``, ``climatology.json``,
``uncertainty.json``, ``scenarios.json``, ``sources.json``, ``metrics.json``.
When ``NEXT_PUBLIC_API_BASE`` points at this backend it requests
``${API_BASE}/<file>`` (see ``urlFor`` in api.ts), so we expose each artifact at
BOTH its bare filename (``/metadata.json``) and a namespaced ``/api/...`` path.

Responses are returned **verbatim** from the in-memory store (no reshaping) so
they are byte-identical to ``CONTRACT.md`` / ``frontend/lib/types.ts``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..data_store import DataStore, get_store

router = APIRouter(tags=["artifacts"])


def _artifact_or_404(store: DataStore, name: str):
    data = store.get_artifact(name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{name}' not loaded")
    return data


# --------------------------------------------------------------------------- #
# Namespaced /api/* paths (richer convention, used by the dashboard panels).
# --------------------------------------------------------------------------- #
@router.get("/api/metadata", summary="Region, grid, time axis & variable metadata")
def get_metadata(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "metadata")


@router.get("/api/fields_daily", summary="One year of daily fields [t][lat][lon]")
def get_fields_daily(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "fields_daily")


@router.get("/api/climatology", summary="Monthly region means + annual-by-year series")
def get_climatology(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "climatology")


@router.get("/api/uncertainty", summary="Per-cell uncertainty field (0..1)")
def get_uncertainty(var: str | None = None, store: DataStore = Depends(get_store)):
    """Full uncertainty artifact, or a single variable's grid via ``?var=``."""
    unc = _artifact_or_404(store, "uncertainty")
    if var:
        if var not in unc:
            raise HTTPException(status_code=404, detail=f"Unknown var '{var}'")
        return {"lats": unc["lats"], "lons": unc["lons"], var: unc[var]}
    return unc


@router.get("/api/scenarios", summary="What-if controls, physics & presets")
def get_scenarios(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "scenarios")


@router.get("/api/sources", summary="The >=30-source data catalog")
def get_sources(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "sources")


@router.get("/api/metrics", summary="Model-evaluation metrics (stub until trained)")
def get_metrics(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "metrics")


# --------------------------------------------------------------------------- #
# Bare-filename aliases so api.ts urlFor(`${API_BASE}/<file>`) just works.
# --------------------------------------------------------------------------- #
@router.get("/metadata.json", include_in_schema=False)
def metadata_json(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "metadata")


@router.get("/fields_daily.json", include_in_schema=False)
def fields_daily_json(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "fields_daily")


@router.get("/climatology.json", include_in_schema=False)
def climatology_json(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "climatology")


@router.get("/uncertainty.json", include_in_schema=False)
def uncertainty_json(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "uncertainty")


@router.get("/scenarios.json", include_in_schema=False)
def scenarios_json(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "scenarios")


@router.get("/sources.json", include_in_schema=False)
def sources_json(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "sources")


@router.get("/metrics.json", include_in_schema=False)
def metrics_json(store: DataStore = Depends(get_store)):
    return _artifact_or_404(store, "metrics")
