"""
pipeline.ingest
===============
One module per real data source. Every module exposes a

    fetch(bbox, start, end, **kwargs) -> "xarray.Dataset"

style function with a docstring citing the source and its exact access
identifier (GEE asset id / CDS dataset / Earthdata short_name / MOSDAC
datasetId / imdlib handle). Imports of the heavy third-party clients are
**guarded** at call time: if the library, credentials or network are
unavailable, ``fetch`` raises :class:`IngestUnavailable` with an actionable
message and the orchestrator falls back to synthetic generation.

This keeps ``import pipeline.ingest.<source>`` safe even on a machine with
nothing but the standard library installed.
"""

from __future__ import annotations


class IngestUnavailable(RuntimeError):
    """Raised when a real source cannot be fetched (missing lib/creds/network).

    The orchestrator catches this and substitutes synthetic data, so a failed
    real ingestion degrades gracefully instead of aborting the pipeline.
    """


def require(module_name: str, hint: str) -> "object":
    """Import ``module_name`` or raise :class:`IngestUnavailable` with a hint.

    Parameters
    ----------
    module_name:
        Importable module (e.g. ``"ee"``, ``"cdsapi"``, ``"imdlib"``).
    hint:
        How to obtain it, surfaced to the user (e.g. ``"pip install earthengine-api"``).
    """
    import importlib

    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # ImportError or transitive import failures
        raise IngestUnavailable(
            f"'{module_name}' unavailable ({exc}). To enable this source: {hint}"
        ) from exc


__all__ = ["IngestUnavailable", "require"]
