"""
pipeline.config
===============
Single source of truth for the Bharat Climate Twin data pipeline.

Everything that defines *what* we are building — the pilot region, the common
analysis grid, the time window, the variables, the on-disk paths, the H3
resolutions, and the 30+ dataset registry — lives here so the ingest,
harmonize, fusion, export and serving stages all agree.

The blueprint (ARCHITECTURE.md §3, §4, §7) fixes these decisions:

* Common analysis grid  : IMD 0.25°  (EPSG:4326)
* Primary pilot         : Marathwada / central Maharashtra drought belt
                          bbox (W, S, E, N) = [74.0, 17.5, 79.0, 21.0]
* H3 keys              : res 4 for the 0.25° rainfall grid (≈1,770 km² cell),
                          res 2 for national roll-ups, res 3 for 1.0° temp.

This module is **pure standard library** (only ``dataclasses`` / ``datetime``)
so it imports with zero third-party dependencies — important because the
offline-demo path must run without numpy/xarray installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

# ──────────────────────────────────────────────────────────────────────────
# Versioning
# ──────────────────────────────────────────────────────────────────────────
#: Schema/version stamped into every serving artifact (see CONTRACT.md).
CONTRACT_VERSION: str = "1.0"


# ──────────────────────────────────────────────────────────────────────────
# Pilot region + common analysis grid
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class GridSpec:
    """A regular lat/lon grid on EPSG:4326, defined by a bbox + resolution.

    The grid uses **cell-centre** coordinates. ``bbox`` is (W, S, E, N) in
    degrees; cell centres are inset by half a cell from the bbox edges so that
    ``nlon * res`` spans exactly the requested width.
    """

    name: str
    bbox: Tuple[float, float, float, float]  # (west, south, east, north)
    res_deg: float

    @property
    def west(self) -> float:
        return self.bbox[0]

    @property
    def south(self) -> float:
        return self.bbox[1]

    @property
    def east(self) -> float:
        return self.bbox[2]

    @property
    def north(self) -> float:
        return self.bbox[3]

    @property
    def nlon(self) -> int:
        """Number of cell columns spanning the bbox width."""
        return int(round((self.east - self.west) / self.res_deg))

    @property
    def nlat(self) -> int:
        """Number of cell rows spanning the bbox height."""
        return int(round((self.north - self.south) / self.res_deg))

    @property
    def lons(self) -> List[float]:
        """Cell-centre longitudes, west → east."""
        half = self.res_deg / 2.0
        return [round(self.west + half + i * self.res_deg, 6) for i in range(self.nlon)]

    @property
    def lats(self) -> List[float]:
        """Cell-centre latitudes, south → north (IMD ``.grd`` ordering)."""
        half = self.res_deg / 2.0
        return [round(self.south + half + j * self.res_deg, 6) for j in range(self.nlat)]

    @property
    def shape(self) -> Tuple[int, int]:
        """(nlat, nlon) — the field shape used throughout the pipeline."""
        return (self.nlat, self.nlon)


# Primary pilot — Marathwada drought belt at the common 0.25° analysis grid.
# nlon = (79.0-74.0)/0.25 = 20 ; nlat = (21.0-17.5)/0.25 = 14  → 20×14 = 280 cells.
MARATHWADA = GridSpec(
    name="Marathwada drought belt (central Maharashtra)",
    bbox=(74.0, 17.5, 79.0, 21.0),
    res_deg=0.25,
)

# Secondary pilot — Kerala / Western Ghats heavy-rain belt (kept for scale-up).
KERALA = GridSpec(
    name="Kerala / Western Ghats heavy-rain belt",
    bbox=(74.5, 8.0, 77.5, 13.0),
    res_deg=0.25,
)

#: The grid the PoC actually builds against.
GRID: GridSpec = MARATHWADA


# ──────────────────────────────────────────────────────────────────────────
# Time window
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TimeSpec:
    """Daily time axis for the cube.

    ``fields_daily.json`` carries exactly ONE representative year (to stay well
    under the size budget); the multi-year climatology spans ``clim_start_year``
    .. ``clim_end_year`` for the interannual / ENSO-like story.
    """

    freq: str = "daily"
    sample_year: int = 2023  # the representative year exported to fields_daily.json
    clim_start_year: int = 2010
    clim_end_year: int = 2023

    @property
    def start(self) -> date:
        return date(self.sample_year, 1, 1)

    @property
    def end(self) -> date:
        return date(self.sample_year, 12, 31)

    @property
    def clim_years(self) -> List[int]:
        return list(range(self.clim_start_year, self.clim_end_year + 1))


TIME: TimeSpec = TimeSpec()


# ──────────────────────────────────────────────────────────────────────────
# Variables (PoC = rainfall + Tmax + Tmin) and their display metadata
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class VariableSpec:
    key: str
    long_name: str
    units: str
    cmap: str
    vmin: float
    vmax: float


VARIABLES: Dict[str, VariableSpec] = {
    "rainfall": VariableSpec("rainfall", "Daily rainfall", "mm/day", "rain", 0.0, 80.0),
    "tmax": VariableSpec("tmax", "Daily maximum 2 m air temperature", "°C", "temp", 15.0, 48.0),
    "tmin": VariableSpec("tmin", "Daily minimum 2 m air temperature", "°C", "temp", 5.0, 32.0),
}

#: Canonical ordering used when serialising variables.
VARIABLE_ORDER: List[str] = ["rainfall", "tmax", "tmin"]


# ──────────────────────────────────────────────────────────────────────────
# H3 spatial indexing resolutions (ARCHITECTURE.md §3.3, §7.4)
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class H3Spec:
    res_map: int = 4      # 0.25° rainfall grid  (avg cell ≈ 1,770 km²)
    res_temp: int = 3     # 1.0° temperature grid
    res_region: int = 2   # national roll-ups


H3 = H3Spec()


# ──────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Paths:
    """Filesystem layout. ``root`` is the repo root (parent of ``pipeline/``)."""

    root: Path = Path(__file__).resolve().parent.parent

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw(self) -> Path:
        """Heavy raw downloads (git-ignored)."""
        return self.data / "raw"

    @property
    def processed(self) -> Path:
        return self.data / "processed"

    @property
    def sample(self) -> Path:
        """Committed JSON serving artifacts (the offline-demo dataset)."""
        return self.processed / "sample"

    @property
    def zarr_cube(self) -> Path:
        return self.processed / "cube.zarr"

    @property
    def cog_dir(self) -> Path:
        return self.processed / "cog"

    @property
    def frontend_public_data(self) -> Path:
        """Second copy of the JSON artifacts the Next.js app serves statically."""
        return self.root / "frontend" / "public" / "data"

    def ensure(self) -> None:
        """Create the output directories that the pipeline writes into."""
        for p in (self.raw, self.processed, self.sample, self.frontend_public_data):
            p.mkdir(parents=True, exist_ok=True)


PATHS = Paths()

#: The artifact filenames defined by CONTRACT.md, in build order.
ARTIFACTS: List[str] = [
    "metadata.json",
    "fields_daily.json",
    "climatology.json",
    "uncertainty.json",
    "scenarios.json",
    "sources.json",
    "metrics.json",
]


# ──────────────────────────────────────────────────────────────────────────
# What-if scenario physics (CONTRACT.md → scenarios.json)
# ──────────────────────────────────────────────────────────────────────────
#: Clausius–Clapeyron scaling — heavy-rain intensity rises ~7 %/°C of warming.
CLAUSIUS_CLAPEYRON_PCT_PER_DEGC: float = 7.0


# ──────────────────────────────────────────────────────────────────────────
# Dataset registry — the 30+ cross-validating sources (ARCHITECTURE.md §4.1,
# research/01 §14, research/06). Each entry carries the EXACT machine-readable
# access identifier so ``ingest/*.py`` and the "Data Sources" UI panel agree.
#
# ``access`` codes:
#   GEE      Google Earth Engine asset id        (ee.ImageCollection)
#   CDS      Copernicus Climate Data Store        (cdsapi dataset id)
#   EA       NASA Earthdata short_name            (earthaccess)
#   MPC      Microsoft Planetary Computer STAC     (pystac-client collection)
#   S3       Anonymous AWS Open Data bucket
#   MOSDAC   ISRO SAC mdapi.py datasetId
#   IMDLIB   imdlib variable handle
#   PORTAL   Web portal / OGC / REST endpoint
# ──────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DatasetSpec:
    name: str
    type: str       # satellite | reanalysis | gauge | merged | model | hydrology | geo
    role: str       # short human-readable role in the twin
    res: str        # spatial / temporal resolution
    provider: str
    access: str      # "<CHANNEL>:<identifier>"


def _ds(name: str, type_: str, role: str, res: str, provider: str, access: str) -> DatasetSpec:
    return DatasetSpec(name=name, type=type_, role=role, res=res, provider=provider, access=access)


#: 44 sources (≥30 mandate met). Indian-origin sources are foregrounded first.
DATASETS: List[DatasetSpec] = [
    # ── Indian national datasets (mandated anchor + INSAT + reanalysis) ──
    _ds("IMD Gridded Rainfall 0.25°", "gauge", "ANCHOR TRUTH (rainfall)",
        "0.25°, daily, 1901–", "IMD Pune", "IMDLIB:rain"),
    _ds("IMD Gridded Tmax 1.0°", "gauge", "ANCHOR TRUTH (Tmax)",
        "1.0°, daily, 1951–", "IMD Pune", "IMDLIB:tmax"),
    _ds("IMD Gridded Tmin 1.0°", "gauge", "ANCHOR TRUTH (Tmin)",
        "1.0°, daily, 1951–", "IMD Pune", "IMDLIB:tmin"),
    _ds("IMD AWS/ARG network", "gauge", "Point validation / downscaling",
        "stations, sub-daily NRT", "IMD", "PORTAL:mausam.imd.gov.in"),
    _ds("IMD merged satellite-gauge rainfall", "merged", "Benchmark product",
        "0.25°, daily", "IMD Pune", "PORTAL:imdpune.gov.in/Rainfall_25_NetCDF_Merged"),
    _ds("INSAT-3D/3DR/3DS LST (3RIMG_L2B_LST)", "satellite", "High-cadence skin-T",
        "4 km, 30-min", "ISRO / MOSDAC", "MOSDAC:3RIMG_L2B_LST"),
    _ds("INSAT-3D SST (3RIMG_L2B_SST)", "satellite", "Diurnal SST",
        "4 km, 30-min", "ISRO / MOSDAC", "MOSDAC:3RIMG_L2B_SST"),
    _ds("INSAT-3D Rainfall (3RIMG_L2B_IMC)", "satellite", "Geostationary QPE",
        "~4 km, 30-min", "ISRO / MOSDAC", "MOSDAC:3RIMG_L2B_IMC"),
    _ds("INSAT-3D/3DR/3DS Imager L1C", "satellite", "Cloud/WV/Tb backbone",
        "1 km VIS, 4 km IR, 15-min", "ISRO / MOSDAC", "MOSDAC:3RIMG_L1C_ASIA_MER"),
    _ds("IMDAA regional reanalysis", "reanalysis", "India-specific reanalysis / training",
        "12 km, hourly, 1979–2020", "NCMRWF", "PORTAL:rds.ncmrwf.gov.in"),
    _ds("Oceansat-3 OSCAT-3 / OCM-3", "satellite", "Winds / ocean context for monsoon",
        "25 km / 1 km", "ISRO / MOSDAC", "MOSDAC:OCEANSAT3"),
    _ds("Megha-Tropiques SAPHIR", "satellite", "Tropical humidity profiles",
        "10 km, multi/day", "ISRO-CNES / MOSDAC", "MOSDAC:SAPHIR_L2"),
    _ds("Bhuvan (NRSC OGC)", "model", "Admin/LULC overlays + basemap",
        "varies", "NRSC / ISRO", "PORTAL:bhuvan.nrsc.gov.in"),
    _ds("NICES (NRSC) ECVs", "model", "Indian climate ECVs (validation)",
        "1–5 km", "NRSC / ISRO", "PORTAL:nices via Bhuvan/MOSDAC"),
    _ds("India-WRIS", "hydrology", "Hydrology ground truth / water balance",
        "basin / station", "CWC + ISRO", "PORTAL:indiawris.gov.in"),

    # ── Global precipitation (fill IMD gauge gaps in space/time) ──
    _ds("GPM IMERG V07", "satellite", "Primary satellite rainfall; TC member",
        "0.1°, 30-min", "NASA / JAXA", "GEE:NASA/GPM_L3/IMERG_V07"),
    _ds("GSMaP v7 operational", "satellite", "Independent MW+IR rainfall",
        "0.1°, hourly", "JAXA", "GEE:JAXA/GPM_L3/GSMaP/v7/operational"),
    _ds("CHIRPS v2 daily", "merged", "Station-blended rainfall (transitional zones)",
        "0.05°, daily", "UCSB-CHG", "GEE:UCSB-CHG/CHIRPS/DAILY"),
    _ds("CMORPH v1 CDR", "satellite", "MW-propagated IR rainfall (independent algo)",
        "8 km / 0.25°", "NOAA CPC", "GEE:NOAA/CDR/CMORPH/V1"),
    _ds("PERSIANN-CDR", "satellite", "ANN IR rainfall, long CDR (ML-friendly)",
        "0.25°, daily", "UC Irvine CHRS", "GEE:NOAA/PERSIANN-CDR"),
    _ds("MSWEP v3", "merged", "SOTA merged benchmark for our fused product",
        "0.1°, 3-hourly", "GloH2O", "PORTAL:gloh2o.org/mswep"),
    _ds("TRMM 3B42 (legacy)", "satellite", "Pre-GPM historical rainfall record",
        "0.25°, 3-hourly", "NASA", "GEE:TRMM/3B42"),

    # ── Global reanalyses (gap-free physics fill) ──
    _ds("ERA5", "reanalysis", "Gap-free backbone; TC member",
        "0.25°, hourly, 1940–", "ECMWF / C3S", "CDS:reanalysis-era5-single-levels"),
    _ds("ERA5-Land", "reanalysis", "Best gap-free 2 m T; LST bias-correction; TC member",
        "9 km, hourly, 1950–", "ECMWF / C3S", "GEE:ECMWF/ERA5_LAND/DAILY_AGGR"),
    _ds("MERRA-2", "reanalysis", "Aerosol-aware independent reanalysis (spread)",
        "0.5°×0.625°, hourly", "NASA GMAO", "EA:M2T1NXSLV"),
    _ds("NCEP/NCAR Reanalysis 1", "reanalysis", "Long independent baseline for TC",
        "~1.9°, 6-hourly, 1948–", "NOAA PSL", "PORTAL:psl.noaa.gov/data/reanalysis"),
    _ds("JRA-3Q", "reanalysis", "Asian-centric independent reanalysis member",
        "~0.375°, 3-hourly", "JMA", "PORTAL:JMA/DIAS"),
    _ds("GLDAS-2 Noah", "reanalysis", "Land-surface states for hydrology/feedback",
        "0.25°, 3-hourly", "NASA", "GEE:NASA/GLDAS/V021/NOAH/G025/T3H"),

    # ── Temperature / Land-Surface-Temperature (multi-sensor) ──
    _ds("MODIS Terra MOD11A1 LST", "satellite", "Fine LST truth; TC member; bias-correct INSAT",
        "1 km, daily (4×/day)", "NASA LP DAAC", "GEE:MODIS/061/MOD11A1"),
    _ds("MODIS Aqua MYD11A1 LST", "satellite", "Fine LST truth (afternoon overpass)",
        "1 km, daily", "NASA LP DAAC", "GEE:MODIS/061/MYD11A1"),
    _ds("VIIRS VNP21A1D LST", "satellite", "MODIS-continuity LST; diurnal constraint",
        "1 km, daily", "NASA LP DAAC", "GEE:NASA/VIIRS/002/VNP21A1D"),
    _ds("Landsat 8/9 ST (TIRS)", "satellite", "Fine-scale LST downscaling covariate",
        "100 m, ~8-day", "USGS / NASA", "MPC:landsat-c2-l2"),
    _ds("ECOSTRESS (ISS)", "satellite", "Ultra-high-res diurnal LST (city/field)",
        "~70 m, irregular", "NASA", "EA:ECO_L2T_LSTE"),
    _ds("Sentinel-3 SLSTR LST", "satellite", "European independent LST/SST",
        "1 km, 1–2 day", "ESA / Copernicus", "MPC:sentinel-3-slstr-lst-l2-netcdf"),
    _ds("NOAA OISST v2.1", "satellite", "Gap-free SST baseline for INSAT SST",
        "0.25°, daily", "NOAA", "GEE:NOAA/CDR/OISST/V2_1"),

    # ── Soil moisture (drives T–P feedback; SM triple-collocation) ──
    _ds("SMAP L4 (SPL4SMGP)", "satellite", "Assimilated soil moisture + soil-T (under-cloud T fill)",
        "9 km, 3-hourly", "NASA NSIDC", "GEE:NASA/SMAP/SPL4SMGP/008"),
    _ds("ASCAT (H SAF)", "satellite", "Independent (active) soil moisture; SM TC member",
        "12.5 km, daily", "EUMETSAT", "PORTAL:H SAF / EUMETSAT"),
    _ds("ESA CCI Soil Moisture v09", "merged", "40-yr merged SM ECV (built on TC)",
        "0.25°, daily", "ESA CCI", "CDS:satellite-soil-moisture"),

    # ── SAR / gravity / optical context ──
    _ds("Sentinel-1 GRD", "satellite", "All-weather flood / soil-moisture context",
        "10 m, 6–12 day", "ESA / Copernicus", "GEE:COPERNICUS/S1_GRD"),
    _ds("GRACE-FO mascon", "satellite", "Water-storage anomaly (drought, rain-independent)",
        "~3°, monthly", "NASA JPL", "GEE:NASA/GRACE/MASS_GRIDS_V04/MASCON"),
    _ds("Sentinel-2 L2A", "satellite", "NDVI / land-cover downscaling covariate",
        "10–60 m, ~5-day", "ESA / Copernicus", "GEE:COPERNICUS/S2_SR_HARMONIZED"),

    # ── Independent geostationary cross-checks over India ──
    _ds("Meteosat MSG/MTG (IODC 45.5°E)", "geo", "Independent geo directly viewing India",
        "1–3 km, 15-min", "EUMETSAT", "PORTAL:EUMETSAT Data Store"),
    _ds("Himawari-8/9 AHI", "geo", "Independent geo (eastern edge) algorithm cross-check",
        "0.5–2 km, 10-min", "JMA", "S3:noaa-himawari9"),
    _ds("FengYun-4A/4B AGRI", "geo", "Independent Asian geo covering India",
        "0.5–4 km, 15-min", "CMA", "PORTAL:satellite.nsmc.org.cn"),
]


def datasets_used_count() -> int:
    """Number of registry sources (the 'never single-source' ledger)."""
    return len(DATASETS)


# ──────────────────────────────────────────────────────────────────────────
# Triple-collocation triplets (mandatory independent error structures, §4.3)
# ──────────────────────────────────────────────────────────────────────────
#: variable -> ordered triplet of (registry-name, role) describing the three
#: pseudo-independent sources fused for the uncertainty estimate.
TC_TRIPLETS: Dict[str, List[Tuple[str, str]]] = {
    "rainfall": [
        ("IMD Gridded Rainfall 0.25°", "gauge"),
        ("GPM IMERG V07", "satellite (passive-MW+IR)"),
        ("ERA5-Land", "reanalysis (model)"),
    ],
    "tmax": [
        ("IMD Gridded Tmax 1.0°", "gauge"),
        ("MODIS Terra MOD11A1 LST", "satellite (IR polar)"),
        ("ERA5-Land", "reanalysis (skin-T)"),
    ],
    "tmin": [
        ("IMD Gridded Tmin 1.0°", "gauge"),
        ("VIIRS VNP21A1D LST", "satellite (IR polar)"),
        ("ERA5-Land", "reanalysis (skin-T)"),
    ],
}
