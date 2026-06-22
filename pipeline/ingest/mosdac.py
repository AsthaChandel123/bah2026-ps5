"""
pipeline.ingest.mosdac
======================
INSAT-3D/3DR/3DS via ISRO MOSDAC — the mandated Indian-satellite "badge" layer
(ARCHITECTURE.md §4.1 #6–9; research/01 §1.1, research/06 §2).

This is the **highest-friction** mandated source: MOSDAC requires an approved
account, locks out after 3 failed logins, and caps downloads at 5000 files/day.
So we model the official ``mdapi.py`` workflow (search → authenticate → download
→ logout) driven by a ``config.json``, and read the resulting HDF5 with ``h5py``.
If credentials/network/libs are unavailable, ``fetch`` raises
:class:`IngestUnavailable` and the orchestrator falls back to MODIS LST (the
documented instant mirror, research/06 §2.5) or synthetic.

Datasets (Imager 3RIMG L2B, HDF5, 4 km, 30-min):
    ``3RIMG_L2B_LST``  Land Surface Temperature
    ``3RIMG_L2B_SST``  Sea Surface Temperature
    ``3RIMG_L2B_IMC``  Imager cloud / hydro-estimator QPE

Manual / API: https://www.mosdac.gov.in/downloadapi-manual
Signup (approval required): https://mosdac.gov.in/signup/
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Tuple

from . import IngestUnavailable, require

DATASET_IDS = ("3RIMG_L2B_LST", "3RIMG_L2B_SST", "3RIMG_L2B_IMC")
MDAPI_URL = "https://www.mosdac.gov.in/software/mdapi.zip"


def write_config(
    bbox: Tuple[float, float, float, float],
    start: date,
    end: date,
    dataset_id: str = "3RIMG_L2B_LST",
    *,
    username: str = "YOUR_USERNAME",
    password: str = "YOUR_PASSWORD",
    download_path: str = "./data/raw/mosdac",
    count: int = 50,
    out_path: str = "./data/raw/mosdac_config.json",
) -> str:
    """Write the ``config.json`` consumed by MOSDAC's ``mdapi.py``.

    ``boundingBox`` is ``minLon,minLat,maxLon,maxLat`` per the official manual.
    Returns the path written. (Credentials should come from the environment in
    real use; ``config.json`` is git-ignored.)
    """
    if dataset_id not in DATASET_IDS:
        raise ValueError(f"dataset_id must be one of {DATASET_IDS}, got {dataset_id!r}")
    w, s, e, n = bbox
    cfg = {
        "user_credentials": {"username": username, "password": password},
        "search_parameters": {
            "datasetId": dataset_id,
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
            "count": str(count),
            "boundingBox": f"{w},{s},{e},{n}",
            "gId": "",
        },
        "download_settings": {
            "download_path": download_path,
            "organize_by_date": True,
            "skip_user_prompt": True,
            "generate_error_log": True,
            "error_log_path": "./data/raw/mosdac_logs",
        },
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(cfg, indent=2))
    return out_path


def fetch(
    bbox: Tuple[float, float, float, float],
    start: date,
    end: date,
    dataset_id: str = "3RIMG_L2B_LST",
    mdapi_path: str | None = None,
):
    """Download + read an INSAT-3D L2B product via the MOSDAC ``mdapi.py`` workflow.

    Steps modelled (research/06 §2.3):
      1. Ensure ``mdapi.py`` + ``config.json`` exist (``write_config``).
      2. Run ``mdapi.py`` (search → authenticate → download → logout).
      3. Read the downloaded HDF5 with ``h5py`` into an xarray.Dataset.

    Raises :class:`IngestUnavailable` whenever the account/network/libs are not
    set up (the common case) so the orchestrator can fall back to MODIS LST.

    Returns
    -------
    xarray.Dataset
        The INSAT L2B field over the bbox (when available).
    """
    require("requests", "pip install requests  (mdapi.py dependency)")
    h5py = require("h5py", "pip install h5py  (read INSAT-3D L2B HDF5)")

    config_path = write_config(bbox, start, end, dataset_id)

    if mdapi_path is None or not Path(mdapi_path).exists():
        raise IngestUnavailable(
            "MOSDAC mdapi.py not found. Download it once from "
            f"{MDAPI_URL} (unzip), create an approved MOSDAC account "
            "(https://mosdac.gov.in/signup/), put credentials in "
            f"{config_path}, then pass mdapi_path=... . Falling back to the "
            "MODIS LST mirror (research/06 §2.5)."
        )

    # Live path (only reached when an operator has provisioned mdapi.py + creds).
    import subprocess  # noqa: PLC0415 - intentional, live path only

    try:
        subprocess.run(["python", mdapi_path], check=True, cwd=Path(mdapi_path).parent)
    except Exception as exc:
        raise IngestUnavailable(f"mdapi.py run failed ({exc}).") from exc

    files = sorted(Path("./data/raw/mosdac").rglob("*.h5"))
    if not files:
        raise IngestUnavailable(
            "MOSDAC download produced no HDF5 files (auth/approval/cap?)."
        )
    return _read_hdf5(h5py, files[0], dataset_id)


def _read_hdf5(h5py, path: Path, dataset_id: str):
    """Read an INSAT-3D L2B HDF5 into an xarray.Dataset (research/06 §2.4)."""
    xr = require("xarray", "pip install xarray")
    np = require("numpy", "pip install numpy")

    var = dataset_id.split("_")[-1]  # LST / SST / IMC
    with h5py.File(path, "r") as f:
        # dataset names vary by product; LST/SST commonly named after the product.
        key = var if var in f else next(iter(f.keys()))
        data = np.asarray(f[key][:], dtype="float64")
        fill = f[key].attrs.get("_FillValue", -999.0)
        data = np.where(data == fill, np.nan, data)
        lat = np.asarray(f["Latitude"][:]) if "Latitude" in f else None
        lon = np.asarray(f["Longitude"][:]) if "Longitude" in f else None

    coords = {}
    dims = ("lat", "lon")
    if lat is not None and lon is not None and lat.ndim == 1 and lon.ndim == 1:
        coords = {"lat": lat, "lon": lon}
    ds = xr.Dataset({var.lower(): (dims, data)}, coords=coords)
    ds.attrs.update(source=f"INSAT-3D {dataset_id} (MOSDAC)", crs="EPSG:4326")
    return ds


__all__ = ["fetch", "write_config", "DATASET_IDS", "MDAPI_URL"]
