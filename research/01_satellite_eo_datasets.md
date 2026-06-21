# Satellite & Earth-Observation Datasets Catalog
### ISRO Bharatiya Antariksh Hackathon 2026 — Problem Statement 5: AI-Powered Digital Twin of India's Climate

**Document scope:** Exhaustive catalog of Indian + global Earth-observation missions and climate datasets relevant to a **rainfall + temperature** digital-twin PoC over an Indian pilot region. Built per the explicit mandate to **never rely on a single source** and to assemble **30+ cross-validatable data sources** spanning satellites, reanalyses, and in-situ gridded products from around the world.

**Compiled:** 2026-06-21. Sources prioritized 2023–2026. All asset IDs / bucket names / portal URLs below are stated explicitly so they can be pasted into code.

**Reading the access column:** `GEE` = Google Earth Engine asset ID (use `ee.ImageCollection("…")`); `CDS` = Copernicus Climate Data Store (use `cdsapi`); `Earthdata/GES DISC/PO.DAAC/NSIDC LP DAAC` = NASA (use `earthaccess`); `MPC` = Microsoft Planetary Computer STAC (use `pystac-client` + `planetary-computer`); `AWS` = anonymous S3 Open Data bucket; `MOSDAC` = ISRO SAC portal (account + Data Download API).

---

## 0. TL;DR coverage map (which source gives you what)

| Variable for the twin | Primary Indian source | Best global satellite | Best reanalysis (continuous, gap-free) | Best in-situ/gauge truth |
|---|---|---|---|---|
| **Rainfall** | IMD 0.25° gridded; INSAT-3D IMC/Hydro-Estimator | GPM IMERG (0.1°, 30-min); GSMaP | ERA5 / ERA5-Land; IMDAA (12 km) | IMD gauge grid; IMD AWS/ARG network |
| **Surface (2 m) air temperature** | IMD 1.0° Tmax/Tmin gridded | (derived) | **ERA5-Land 2 m T (9 km, hourly)**; IMDAA | IMD AWS network |
| **Land Surface Temperature (skin)** | INSAT-3D/3DR/3DS LST (4 km, 30-min) | MODIS MOD11/MYD11 (1 km); VIIRS VNP21 (1 km); Landsat ST (100 m); ECOSTRESS (70 m) | ERA5-Land skin temp | n/a |
| **Sea Surface Temperature** | INSAT-3D SST; Oceansat-3 SSTM (offline) | MODIS SST; Sentinel-3 SLSTR; AVHRR/OISST | ERA5 SST | buoys |
| **Soil moisture (drives T & P feedback)** | (RISAT, limited) | SMAP (9 km); ASCAT; SMOS | ERA5-Land; GLDAS | ESA CCI SM (merged) |
| **Cloud / monsoon convection (geo)** | INSAT-3D/3DR/3DS imager (15-min) | Himawari-9; Meteosat MSG/MTG; GOES; FengYun-4 | n/a | n/a |
| **Terrestrial water storage** | India-WRIS | GRACE / GRACE-FO | GLDAS | India-WRIS gauges |

> Counting below: **40+ distinct missions/datasets** are cataloged, comfortably exceeding the 30-source mandate.

---

## 1. INDIAN MISSIONS & NATIONAL DATASETS (mandated core)

### 1.1 INSAT geostationary series — the heart of the Indian observation system

INSAT-3D (2013), INSAT-3DR (2016) and INSAT-3DS (launched **17-Feb-2024**, GSLV-F14) are co-located geostationary meteorological satellites. Together they give an effective **~15-minute** refresh of India + Indian Ocean (a new imager set every 15 min when staggered). INSAT-3DS adds black-body-calibration and mid-night-sun-intrusion fixes over 3D/3DR. Each carries a 6-channel **Imager** and a 19-channel **Sounder**.

**Imager channel resolutions (key for thermal/LST/rainfall):**
- VIS (0.55–0.75 µm) & SWIR (1.55–1.70 µm): **1 km**
- MIR (3.80–4.00 µm), WV (6.50–7.10 µm), TIR-1 (10.3–11.3 µm), TIR-2 (11.5–12.5 µm): **4 km**

| Source | Measures (rain/temp) | Spatial res | Temporal / latency | Coverage | Format | Access (exact) | License/Auth | Cross-validation value |
|---|---|---|---|---|---|---|---|---|
| **INSAT-3D/3DR/3DS Imager L1C** | Raw radiances → cloud, WV, brightness temp | 1 km (VIS/SWIR), 4 km (IR) | 30 min/satellite; ~15 min combined; NRT | Full disk (India + Indian Ocean, ~Asia) | HDF5 | MOSDAC portal + **Data Download API** (config.json) | Free; MOSDAC account + approval | Geostationary backbone; fills time gaps between polar overpasses |
| **INSAT-3D LST** `3RIMG_L2B_LST` | Land Surface Temperature | **4 km** | **30 min**, NRT | Indian landmass / disk | HDF5, KML | MOSDAC product page `mosdac.gov.in/doi/190/`; Data Download API | Free + account | High-cadence LST; diurnal cycle that polar MODIS/VIIRS miss |
| **INSAT-3D SST** `3RIMG_L2B_SST` | Sea Surface Temperature | **4 km** | **30 min**, NRT | N. Indian Ocean / disk | HDF5, KML | MOSDAC; Data Download API | Free + account | Diurnal SST; cross-check vs MODIS/Sentinel-3 |
| **INSAT-3D Rainfall (IMC / Hydro-Estimator)** `3RIMG_L2B_IMC` | Quantitative Precipitation Estimation (QPE) from TIR/WV | ~4 km (10 km QPE class) | 30 min, NRT | Disk | HDF5 | MOSDAC; Data Download API | Free + account | Geostationary rain rate; merges with IMERG/GSMaP to fill 30-min gaps |
| **INSAT-3D Sounder L2** | Temperature & humidity vertical profiles | ~10 km | hourly | Disk | HDF5 | MOSDAC | Free + account | 3-D thermodynamic state for assimilation |
| **INSAT-3D Outgoing LW Radiation / Cloud products** | Convection proxy for monsoon rainfall | 4–8 km | 30 min | Disk | HDF5 | MOSDAC | Free + account | Convective intensity → rainfall nowcasting |

**INSAT data Levels:** L0 (raw), L1 (standard/geo-located), L2 (geophysical: LST/SST/QPE/profiles), L3 (binned/gridded).
**MOSDAC Data Download API:** driven by a `config.json` (credentials + product + date range); authenticates with MOSDAC account. Manual: `mosdac.gov.in/downloadapi-manual`; spec PDF `mosdac.gov.in/sites/default/files/docs/MOSDAC_Satellite_Data_Download_API.pdf`. Account signup `mosdac.gov.in/signup/` (approval required; 1-hour lockout after 3 bad logins). Also fully open-access derived products at `mosdac.gov.in/open-data`.

### 1.2 Other Indian missions

| Source | Measures (rain/temp) | Spatial res | Temporal / latency | Coverage | Format | Access (exact) | License/Auth | Cross-validation value |
|---|---|---|---|---|---|---|---|---|
| **Oceansat-3 / EOS-06 — OCM-3** | Ocean colour, Chl-a, AOD (indirect aerosol→radiation) | 1 km (global), 360 m (local) | 2-day global revisit | Global | HDF5/GeoTIFF | MOSDAC `mosdac.gov.in/oceansat-3`; Bhuvan | Free + account | Aerosol/ocean context; AOD affects T retrievals |
| **Oceansat-3 — OSCAT-3 (Ku scatterometer)** | Sea-surface wind speed/vector | 25 km, 1440 km swath | ~2-day | Global ocean | HDF5 | MOSDAC; Bhuvan | Free + account | Winds modulate moisture transport → monsoon rainfall |
| **Oceansat-3 — SSTM** | SST (2-channel) | — | — | Global | HDF5 | MOSDAC | **Currently NON-operational** (scan-mechanism fault) | Use INSAT/MODIS SST instead |
| **Oceansat-2 — OCM-2 / OSCAT** | Ocean colour; winds (scatterometer failed 2014) | 360 m / 1 km; 25–50 km | legacy archive | Global | HDF5 | MOSDAC | Free + account | Historical wind/ocean record |
| **SCATSAT-1** | Ocean-surface wind vectors (Ku scatterometer) | 25 km / 50 km | ~daily | Global ocean | HDF5 | MOSDAC | Free + account | Wind climatology for monsoon onset diagnostics |
| **Megha-Tropiques — SAPHIR** | 6-layer water-vapour humidity profiles (183 GHz) | 10 km | tropical, multiple/day | ±30° tropics (incl. India) | HDF/NetCDF | **MOSDAC** + **AERIS/ICARE** (`aeris-data.fr`) | Free + account | Tropical humidity → rainfall; assimilation input |
| **Megha-Tropiques — MADRAS** | Microwave imager: precip, cloud liquid, SST wind | ~10–40 km | tropical | ±30° tropics | HDF | MOSDAC/ICARE | Free (MADRAS degraded later in mission) | Passive-MW rain over tropics |
| **Megha-Tropiques — ScaRaB** | Radiation budget (SW/LW) | 40 km | tropical | ±30° tropics | HDF/NetCDF | MOSDAC/ICARE | Free + account | Energy-budget closure for the twin |
| **RISAT-1A / RISAT-2B (SAR)** | C/X-band SAR → soil moisture, flood, surface water | 1–50 m | ~12–25 day repeat | India focus | CEOS/GeoTIFF | MOSDAC / NRSC Bhuvan (restricted) | Account; some restricted | Soil-moisture & inundation context |
| **Cartosat-1/2/3** | High-res optical (DEM, land cover) | 0.25–2.5 m | task-based | India | GeoTIFF | Bhuvan / NRSC | Account; some restricted | Static land-surface/terrain layer for downscaling |
| **EOS-04 / RISAT-1A** | C-band SAR (all-weather) | up to 1 m | — | India | — | MOSDAC/NRSC | Account | All-weather surface state |
| **EOS-08** (2024 microsat) | EOIR / thermal experimental | — | — | — | — | NRSC | Account | Experimental thermal |

### 1.3 IMD national gridded products & in-situ (MANDATED — the ground-truth core)

IMD's gridded daily products are the canonical Indian observational truth; they are the **anchor for bias-correcting every satellite/reanalysis product** below.

| Source | Measures | Spatial res | Temporal / latency | Coverage / grid | Format | Access (exact) | License/Auth | Notes |
|---|---|---|---|---|---|---|---|---|
| **IMD Gridded Rainfall** | Daily rainfall (mm) | **0.25° × 0.25°** | Daily; 1901–present (yearly files, season lag) | India land; **135 × 129** grid; SW corner 6.5N/66.5E → 38.5N/100.0E | binary `.GRD` (Bin), also NetCDF & ASCII | `imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html` (Bin) / `…/Rainfall_25_NetCDF.html`; via **IMDLIB** | Free (registration on portal) | Anchor truth for rainfall |
| **IMD Gridded Max Temp (Tmax)** | Daily max 2 m temp (°C) | **1.0° × 1.0°** | Daily; 1951–present | India; **31 × 31** grid; 7.5N–37.5N, 67.5E–97.5E | binary `.GRD`, NetCDF | `imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html`; IMDLIB (`tmax`) | Free | Anchor truth for max temp |
| **IMD Gridded Min Temp (Tmin)** | Daily min 2 m temp (°C) | **1.0° × 1.0°** | Daily; 1951–present | India; 31 × 31 grid | binary `.GRD`, NetCDF | `imdpune.gov.in/cmpg/Griddata/Min_1_Bin.html`; IMDLIB (`tmin`) | Free | Anchor truth for min temp |
| **IMD AWS / ARG network** | Station rainfall, T, RH, wind, pressure | point (~thousands of stations) | hourly/sub-daily; NRT | India | tabular/API | IMD `mausam.imd.gov.in`; NRT via IMD/SATMET | Free / partly restricted | Point validation for grids & downscaling |
| **IMD SATMET products** | INSAT-derived rain/cloud imagery | 4 km | NRT | India | imagery | `mausam.imd.gov.in/imd_latest/contents/satmet.php` | Free | Operational satellite-met cross-check |

> **Binary-read tip:** IMD `.GRD` rainfall is `135×129` float per day, `366` records max/year; temperature is `31×31`. **IMDLIB** (`pip install imdlib`) reads these directly into `xarray` and exports NetCDF/GeoTIFF — do not hand-roll the binary parser. (Ref: `imdlib.readthedocs.io`, GitHub `iamsaswata/imdlib`.)

### 1.4 Indian regional reanalysis & geoportals (high value, often overlooked)

| Source | Measures | Spatial res | Temporal | Coverage | Format | Access | License/Auth | Notes |
|---|---|---|---|---|---|---|---|---|
| **IMDAA** (NCMRWF + Met Office + IMD) | **Indian-region reanalysis**: 2 m T, precip, winds, humidity, soil (57 vars, 63 levels) | **12 km (0.12°)** | hourly & 3-hourly; 1979–2020 | Indian monsoon region | NetCDF/GRIB | NCMRWF RDS portal `rds.ncmrwf.gov.in` | Free registration | **Best India-specific gap-free reanalysis**; outperforms ERA5 in wet-coastal/NE India |
| **NGFS / NCUM analyses** (NCMRWF) | Operational NWP analysis fields | ~12 km | 6-hourly | India/global | GRIB | NCMRWF | Registration | Operational state for nowcasting |
| **Bhuvan (NRSC/ISRO geoportal)** | NDVI, LST, ocean temp, CartoDEM (30 m), land use | varies | various | India | WMS/WMTS/WCS/WFS/CSW/KML | `bhuvan.nrsc.gov.in`; **Bhuvan APIs** (Search, Statistics, "Codes4All" stacking/NDVI); QGIS "Bhuvan Web Services" plugin | Free; some restricted | OGC services → easy programmatic layers for India |
| **NICES (NRSC)** | Long-term ECV products: NDVI, vegetation, snow, aerosol, energy-balance ET | 1 km–5 km | 8-day/monthly | India + global | GeoTIFF/NetCDF | NICES via Bhuvan/NRSC portal | Free + account | Indian climate ECVs for validation |
| **India-WRIS** (CWC + ISRO) | Hydrology: rainfall, reservoir, groundwater, river flow | basin/station | daily–monthly | India | GIS/CSV/API | `indiawris.gov.in` | Free | Hydrological closure & water-storage cross-check |
| **MOSDAC value-added** | Heavy-rain nowcast, fog, cyclone, SST, soil-wetness | 4 km–25 km | NRT | India/IO | HDF/imagery | `mosdac.gov.in` | Free + account | Operational fused products to benchmark the twin |

---

## 2. GLOBAL REANALYSIS (continuous, gap-free — the "physics fill" layer)

Reanalyses are model+assimilation outputs with **no clouds/no gaps** — essential to fill satellite voids and provide the dynamical backbone of a digital twin.

| Source | Measures (rain/temp) | Spatial res | Temporal / latency | Coverage | Format | Access (exact) | License/Auth | Cross-validation value |
|---|---|---|---|---|---|---|---|---|
| **ERA5** (ECMWF/C3S) | 2 m T, total precip, SST, skin T, winds, soil (100+ vars) | **0.25°** (31 km) | hourly; 1940–present; ~5-day latency (ERA5T preliminary) | Global | GRIB/NetCDF | **CDS API** `cdsapi`, dataset `reanalysis-era5-single-levels`; GEE `ECMWF/ERA5/HOURLY`, `ECMWF/ERA5/DAILY`; AWS `s3://ecmwf-era5` / `era5-pds` | Free; CDS account (ADS token) | The default gap-free backbone |
| **ERA5-Land** | **2 m T**, total precip, soil moisture/temp, ET, runoff (50 vars) | **9 km (0.1°)** | hourly; 1950–present | Global land | GRIB/NetCDF | CDS `reanalysis-era5-land`; **GEE `ECMWF/ERA5_LAND/HOURLY`**, `…/DAILY_AGGR` | Free; CDS account | **Best gap-free 2 m T**; bias-correct INSAT/MODIS LST against this |
| **MERRA-2** (NASA GMAO) | 2 m T, precip, aerosols, radiation | **0.5° × 0.625°** | hourly; 1980–present; ~3-week latency | Global | NetCDF | NASA **GES DISC** (`earthaccess`); GEE `NASA/GSFC/MERRA/*` (slv, flx, rad) | Free; Earthdata login | Aerosol-aware T/precip; independent of ECMWF |
| **NCEP/NCAR Reanalysis 1** | 2 m T, precip, winds | **~1.875°** (T62 Gaussian) | daily/6-hourly; 1948–present; ~1-day | Global | NetCDF | **NOAA PSL** `psl.noaa.gov/data/reanalysis/`; OPeNDAP | Free, open | Long baseline; independent third dataset for triple-collocation |
| **JRA-3Q** (JMA) | 2 m T, precip, winds (successor to JRA-55) | **~0.375° (TL479)** | 3-hourly/6-hourly; 1947–present; NRT (~1 day) | Global | GRIB | JMA Data Dissemination / DIAS | Free; registration | Independent Asian-centric reanalysis |
| **JRA-55** (legacy) | 2 m T, precip | ~0.56° (TL319) | 6-hourly; 1958–2023 | Global | GRIB | JMA/DIAS; NCAR RDA `ds628.0` | Free; registration | Historical baseline |
| **GLDAS-2** (Noah LSM) | Soil moisture/temp, ET, runoff, **2 m T**, rainfall forcing | **0.25°** (also 1.0°) | 3-hourly + monthly; 2000–present; ~1.5 mo | Global land (60S–90N) | NetCDF | GES DISC (`earthaccess`); **GEE `NASA/GLDAS/V021/NOAH/G025/T3H`** | Free; Earthdata | Land-surface states for hydrology/feedback |
| **FLDAS** (famine-warning LDAS) | Soil moisture, ET, **air T**, rainfall | 0.1° / 0.25° | monthly; 1982–present | Africa-centric (+ global runs) | NetCDF | GES DISC (`earthaccess`); GEE `NASA/FLDAS/NOAH01/C/GL/M/V001` | Free; Earthdata | Drought/land-state cross-check |

---

## 3. GLOBAL PRECIPITATION (satellite + merged — fill IMD gauge gaps in space/time)

| Source | Measures | Spatial res | Temporal / latency | Coverage | Format | Access (exact) | License/Auth | Cross-validation value |
|---|---|---|---|---|---|---|---|---|
| **GPM IMERG V07** (NASA/JAXA) | Multi-sat merged precip rate | **0.1°** | **30-min**; Early ~4 h, Late ~14 h, Final ~3.5 mo | 90N–90S (full global in V07) | HDF5/NetCDF | GES DISC: `GPM_3IMERGHH` (Final ½-hr), `GPM_3IMERGHHL` (Late), `GPM_3IMERGHHE` (Early), `GPM_3IMERGDF` (daily), `GPM_3IMERGM` (monthly); `earthaccess`; **AWS** `s3://gpm-imerg…` (e.g. `nasa-gpm3imerghhl`); GEE `NASA/GPM_L3/IMERG_V07` & `…/IMERG_MONTHLY_V07` | Free; Earthdata | **Primary satellite rainfall**; Early run = NRT for the twin |
| **TRMM 3B42 / TMPA** (legacy) | Merged precip (pre-GPM) | 0.25° | 3-hourly; 1998–2019 | 50N–50S | HDF | GES DISC; GEE `TRMM/3B42` | Free; Earthdata | Long historical record pre-2000s |
| **GSMaP** (JAXA, GPM) | Microwave+IR merged rain | **0.1°** | **hourly**; NRT (~4 h) & gauge-adjusted | 60N–60S | NetCDF/binary | JAXA G-Portal/Global Rainfall Watch `sharaku.eorc.jaxa.jp/GSMaP/`; **GEE `JAXA/GPM_L3/GSMaP/v6/operational`** & `v7/operational` & `v6/reanalysis` | Free; JAXA acknowledgment | Independent of IMERG → fusion/triple-collocation |
| **CHIRPS v2 / v3** (UCSB CHC) | IR + station rainfall | **0.05°** | daily/pentad/monthly; 1981–present; ~3-week | 50N–50S, all lon | NetCDF/GeoTIFF | **GEE `UCSB-CHG/CHIRPS/DAILY`** & `…/PENTAD`; v3 `UCSB-CHC/CHIRPS/V3/...`; `chc.ucsb.edu/data/chirps3`; AWS | **Public domain** | High-res, station-blended; great for transitional climates |
| **CMORPH** (NOAA CPC) | MW-propagated IR rain | 8 km / 0.25° | 30-min/3-hr/daily; 1998–present | 60N–60S | binary/NetCDF | NOAA CPC NCEI; GEE `NOAA/CDR/CMORPH/V1` | Free, open | Morphing technique; independent algorithm |
| **PERSIANN / PERSIANN-CDR / PDIR-Now / CCS** (UC Irvine CHRS) | ANN IR rain estimates | 0.25° (0.04° CCS) | hourly–daily; CDR 1983–present | 60N–60S | NetCDF/GeoTIFF | CHRS Data Portal `chrsdata.eng.uci.edu`; GEE `NOAA/PERSIANN-CDR` | Free | Long ANN-based CDR; ML-friendly |
| **MSWEP v3** (GloH2O) | **Merged gauge+sat+reanalysis** "best estimate" | 0.1° | 3-hourly; 1979–present | Global | NetCDF | `gloh2o.org/mswep` (request) | Free for research (registration) | State-of-art merged product to benchmark your own fusion |
| **PERSIANN-PDIR-Now** | NRT IR rain | 0.04° | hourly; ~15-min–1-h latency | 60N–60S | NetCDF | CHRS portal | Free | Very-low-latency NRT option |

---

## 4. GLOBAL TEMPERATURE & LAND-SURFACE TEMPERATURE (LST) — multi-sensor for cloud-gap filling

INSAT LST (4 km, 30-min) is high-cadence but coarse and cloud-contaminated; the polar sensors below give **fine-resolution truth** to bias-correct and downscale it.

| Source | Measures | Spatial res | Temporal / latency | Coverage | Format | Access (exact) | License/Auth | Cross-validation value |
|---|---|---|---|---|---|---|---|---|
| **MODIS Terra MOD11A1 / Aqua MYD11A1** | LST & emissivity (day+night) | **1 km** | daily (4 overpasses/day Terra+Aqua); ~near-real-time + standard | Global | HDF/GeoTIFF | LP DAAC (`earthaccess`); **GEE `MODIS/061/MOD11A1`, `MODIS/061/MYD11A1`** | Free; Earthdata | Workhorse LST truth; 4 daily samples |
| **MODIS MOD11A2 / MYD11A2** | 8-day mean LST | 1 km | 8-day | Global | HDF | GEE `MODIS/061/MOD11A2`, `MODIS/061/MYD11A2` | Free | Gap-reduced composite |
| **MODIS MOD21A1D/N** | LST&E via TES algorithm | 1 km | daily | Global | HDF | LP DAAC; GEE `MODIS/061/MOD21A1D` | Free | Emissivity-explicit, arid-region accuracy |
| **VIIRS VNP21A1D/N (SNPP)** | LST&E day/night | 1 km | daily; 2012–present | Global | HDF/GeoTIFF | LP DAAC (`earthaccess`); **GEE `NASA/VIIRS/002/VNP21A1D`** | Free; Earthdata | MODIS continuity; algorithm twin of MOD21 |
| **VIIRS VNP21A2** | 8-day LST&E | 1 km | 8-day | Global | HDF | LP DAAC; GEE | Free | Composite LST |
| **AIRS L3 (AIRS3STD/AIRS3STM)** | Air temp profiles, surface (skin) T, OLR, humidity | **1.0°** | daily & monthly; 2002–present | Global | HDF/NetCDF | GES DISC (`earthaccess`); GEE `NASA/AIRS/AIRS3STD` (limited) | Free; Earthdata | 3-D atmospheric T/humidity for assimilation |
| **Landsat 8/9 Collection-2 L2 Surface Temp (TIRS)** | LST (Surface Temperature band ST_B10) | **100 m** (resampled 30 m) | 16-day/satellite (~8-day combined) | Global | GeoTIFF/COG | **GEE `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2`**; **MPC `landsat-c2-l2`**; AWS `s3://usgs-landsat` | Free; AWS RequesterPays for some | Fine-scale LST for downscaling INSAT to city/field scale |
| **ECOSTRESS (ISS)** | LST&E, ET | **~70 m** | irregular (ISS orbit), ~1–5 day; 2018–present | ±52° lat (covers India) | HDF/GeoTIFF | LP DAAC (`earthaccess`); MPC; AppEEARS | Free; Earthdata | Ultra-high-res LST + diurnal sampling (drifting overpass) |
| **Sentinel-3 SLSTR L2 LST** | LST (+ SST via WST) | **1 km** | ~1–2 day (A+B) | Global | NetCDF | **MPC `sentinel-3-slstr-lst-l2-netcdf`**; Copernicus Data Space; GEE `COPERNICUS/S3/OLCI` (radiance) | Free; some need CDSE login | European independent LST/SST |
| **MODIS/AVHRR OISST (NOAA OISST v2.1)** | Daily blended SST | 0.25° | daily; 1981–present | Global ocean | NetCDF | NOAA NCEI; GEE `NOAA/CDR/OISST/V2_1` | Free | Gap-free SST baseline for INSAT SST |

---

## 5. OPTICAL / MULTISPECTRAL (land cover, vegetation, downscaling covariates)

| Source | Measures (relevance) | Spatial res | Temporal | Coverage | Format | Access (exact) | License/Auth | Notes |
|---|---|---|---|---|---|---|---|---|
| **Sentinel-2 MSI L2A** | 13-band SR; NDVI, land cover (LST downscaling covariate) | **10/20/60 m** | ~5-day (2A+2B/2C) | Global land | JP2/COG | **GEE `COPERNICUS/S2_SR_HARMONIZED`**; **MPC `sentinel-2-l2a`**; AWS `s3://sentinel-s2-l2a` | Free; AWS RequesterPays | Surface state/NDVI for thermal sharpening |
| **Landsat 8/9 OLI L2 SR** | Surface reflectance, NDVI | 30 m | ~8-day combined | Global | COG | GEE `LANDSAT/LC0{8,9}/C02/T1_L2`; MPC; AWS `usgs-landsat` | Free | Pairs with its own ST band |
| **MODIS MOD13/MYD13 (NDVI/EVI)** | Vegetation indices | 250 m–1 km | 16-day | Global | HDF | GEE `MODIS/061/MOD13Q1` | Free | Veg-T relationship for downscaling |
| **Sentinel-3 OLCI L2 (LFR/WFR)** | Ocean/land colour, vegetation | 300 m | ~1–2 day | Global | NetCDF | MPC `sentinel-3-olci-lfr-l2-netcdf`; CDSE | Free | Independent veg/colour |
| **HLS v2.0 (Harmonized Landsat-Sentinel)** | Harmonized 30 m SR | 30 m | 2–3 day | Global | COG | MPC `hls2-l30`/`hls2-s30`; LP DAAC | Free; Earthdata | Dense 30 m time series |

---

## 6. RADAR / SAR & SOIL MOISTURE (all-weather; soil moisture drives T & P feedback)

| Source | Measures | Spatial res | Temporal / latency | Coverage | Format | Access (exact) | License/Auth | Cross-validation value |
|---|---|---|---|---|---|---|---|---|
| **SMAP L3 (SPL3SMP_E)** | Surface soil moisture (radiometer) | **9 km** | daily (6 am/6 pm); 2015–present | Global | HDF5 | NSIDC DAAC (`earthaccess`); **GEE `NASA/SMAP/SPL3SMP_E/006`** | Free; Earthdata | Soil-moisture state for land-atmosphere coupling |
| **SMAP L4 (SPL4SMGP)** | Surface + root-zone SM, soil T, ET, net radiation (assimilated) | **9 km** | **3-hourly**; ~1–2 wk; 2015–present | Global | HDF5 | NSIDC (`earthaccess`); **GEE `NASA/SMAP/SPL4SMGP/008`** | Free; Earthdata | Gap-free assimilated SM — ideal twin input |
| **Sentinel-1 SAR (GRD/SLC)** | C-band backscatter → soil moisture, flood, water extent | 10 m | 6–12 day | Global | GeoTIFF/COG | **GEE `COPERNICUS/S1_GRD`**; **MPC `sentinel-1-grd` / `sentinel-1-rtc`**; AWS `s3://sentinel-s1-l1c` | Free | All-weather inundation & high-res SM |
| **ASCAT (Metop-A/B/C, H SAF)** | C-band scatterometer surface soil moisture & winds | **12.5 km / 6.25 km** | ~daily; NRT | Global | BUFR/NetCDF | EUMETSAT **H SAF** portal; Copernicus; TU Wien | Free; registration | Independent (active) SM; long record |
| **ESA CCI Soil Moisture v09.x** | **Merged active+passive** SM ECV (5 active + 12 passive sensors) | 0.25° | daily; **1978–present (40+ yr)** | Global | NetCDF | CEDA `catalogue.ceda.ac.uk`; ESA CCI `climate.esa.int/projects/soil-moisture`; CDS | Free; registration | **Long merged SM truth** for triple-collocation |
| **SMOS (ESA)** | L-band soil moisture & ocean salinity | ~25–50 km | ~3-day; 2010–present | Global | NetCDF | ESA; CATDS | Free; registration | Third independent SM sensor |

---

## 7. GRAVITY / WATER STORAGE

| Source | Measures | Spatial res | Temporal | Coverage | Format | Access (exact) | License/Auth | Cross-validation value |
|---|---|---|---|---|---|---|---|---|
| **GRACE / GRACE-FO Mascon (JPL RL06.3 v04)** | Terrestrial water storage anomaly (equiv. water height, cm) | ~3° native (1° grid; mascon ~300 km) | monthly; 2002–2017 (GRACE) + 2018–present (GRACE-FO) | Global | NetCDF | **PO.DAAC** `TELLUS_GRAC-GRFO_MASCON_GRID_RL06.3_V4` (+ CRI variant) (`earthaccess`); **GEE `NASA/GRACE/MASS_GRIDS_V04/MASCON`** | Free; Earthdata | Basin water-balance closure; drought signal independent of rainfall |

---

## 8. GEOSTATIONARY (monsoon / cloud / convection — complements INSAT)

| Source | Measures | Spatial res | Temporal | Coverage | Format | Access (exact) | License/Auth | Cross-validation value |
|---|---|---|---|---|---|---|---|---|
| **Himawari-8/9 AHI (JMA)** | 16-band imager; cloud, WV, brightness T, derived rain | 0.5–2 km | **10-min full disk** | E Asia + W Pacific (partial India edge) | NetCDF/HSD | **AWS `s3://noaa-himawari8` / `noaa-himawari9`** (anonymous); JAXA Himawari Monitor | Free, open | Independent geo over E Indian Ocean; algorithm cross-check vs INSAT |
| **Meteosat MSG / MTG (EUMETSAT)** | SEVIRI/FCI imager; cloud, WV, LST, rain (MPE) | 1–3 km | **15-min (MSG), 10-min (MTG)** | Africa+Europe+**Indian Ocean (IODC at 45.5°E covers India)** | NetCDF/native | EUMETSAT Data Store API/EUMETView; some on AWS | Free; EUMETSAT account | **IODC directly views India** — key independent geo |
| **GOES-16/18/19 ABI (NOAA)** | 16-band imager; cloud, rain (QPE) | 0.5–2 km | 5–15 min | Americas | NetCDF | **AWS `s3://noaa-goes16` / `noaa-goes18` / `noaa-goes19`** (anonymous); `goes2go` lib | Free, open | Algorithm reference (not over India) |
| **FengYun-4A/4B AGRI (CMA)** | Imager; cloud, LST, rain | 0.5–4 km | 15-min | Asia-Pacific (covers India) | HDF | CMA NSMC `satellite.nsmc.org.cn` | Free; registration | Independent Asian geo covering India |
| **NOAA GMGSI** | Global mosaic of all geo sats (composited IR/VIS/WV) | ~8 km | hourly | Global | NetCDF | **AWS `s3://noaa-gmgsi`** (anonymous) | Free, open | One-stop global geo mosaic incl. Meteosat+Himawari |

---

## 9. ATMOSPHERIC COMPOSITION

| Source | Measures (relevance) | Spatial res | Temporal | Coverage | Format | Access (exact) | License/Auth | Notes |
|---|---|---|---|---|---|---|---|---|
| **Sentinel-5P TROPOMI** | NO₂, SO₂, CO, O₃, CH₄, aerosol index/AOD (aerosol→radiation→T) | 5.5 × 3.5 km | daily; 2018–present | Global | NetCDF | **GEE `COPERNICUS/S5P/NRTI/*` & `…/OFFL/*`**; Copernicus Data Space; GES DISC `S5P_L2__AER_AI` | Free; some CDSE login | Aerosol/pollution context for radiative forcing & air-quality twin extension |

---

## 10. HYDROLOGICAL / LAND (evaporation, water resources)

| Source | Measures | Spatial res | Temporal | Coverage | Format | Access | License/Auth | Notes |
|---|---|---|---|---|---|---|---|---|
| **GLEAM v3/v4** | Terrestrial evaporation, transpiration, soil moisture, evaporative stress | 0.25° (v4: 0.1°) | daily/monthly; 1980–present | Global land | NetCDF | `gleam.eu` (request access) | Free for research | ET closure for energy/water budget |
| **GLDAS** (see §2) | Soil moisture/temp, ET, runoff | 0.25° | 3-hourly | Global land | NetCDF | GES DISC; GEE | Free; Earthdata | Land-state ensemble member |
| **India-WRIS** (see §1.4) | Rainfall, reservoir, groundwater, streamflow | basin/station | daily–monthly | India | API/CSV/GIS | `indiawris.gov.in` | Free | Hydrological ground truth |
| **MOD16 / PML_V2 ET** | Evapotranspiration | 500 m–1 km | 8-day | Global | HDF | GEE `MODIS/061/MOD16A2`, `CAS/IGSNRR/PML/V2_v018` | Free | High-res ET for downscaling |

---

## 11. GAP-FILLING & CROSS-VALIDATION STRATEGY

The mandate ("never trust one source") translates into a concrete multi-source fusion + validation pipeline. Below is how to actually wire these datasets together for the rainfall + temperature twin.

### 11.1 Rainfall fusion (gauge ⊕ satellite ⊕ reanalysis)

1. **Anchor on IMD 0.25° gauge grid** as observational truth where gauge density is high (peninsular India). It is the bias reference.
2. **Add high-cadence satellite rainfall** for space-time fill: **GPM IMERG Early (NRT, 30-min, 0.1°)** + **GSMaP (hourly)** + **INSAT-3D IMC/Hydro-Estimator (30-min, geostationary)**. Geostationary INSAT fills the *temporal* gaps between IMERG's microwave overpasses; IMERG/GSMaP fill INSAT's IR-only weakness on rain intensity.
3. **Bias-correct each satellite product to IMD** using quantile mapping / CDF matching at monthly scale per grid cell (well-established for Indian monsoon; satellite IR overestimates light rain, underestimates orographic extremes).
4. **Blend** with weights from **triple collocation** (see 11.3) so each product's weight ∝ 1/error-variance. A documented Indian approach fuses INSAT-3D + IMERG + GSMaP to a **4 km hourly** merged rainfall — mirror this for the PoC.
5. **Fill remaining cloud/no-retrieval voids** with **ERA5 / ERA5-Land / IMDAA** precipitation (gap-free) and, optionally, **CHIRPS v3** (station-blended) in transitional zones where it scores best.
6. **Benchmark your fused product** against **MSWEP v3** (an existing state-of-art merged dataset) — if you beat or match MSWEP regionally, the fusion is sound.

### 11.2 Temperature fusion (2 m air-T and skin/LST)

- **2 m air temperature:** anchor on **IMD 1.0° Tmax/Tmin**; downscale/gap-fill using **ERA5-Land 2 m T (9 km hourly)** and **IMDAA (12 km hourly)**. Use MERRA-2 / NCEP / JRA-3Q as independent members for spread/uncertainty.
- **Land Surface Temperature (skin):** anchor high-cadence on **INSAT-3D LST (4 km, 30-min)** but it is cloud-limited and coarse. **Bias-correct INSAT LST against MODIS MOD11/MYD11 (1 km, 4 overpasses/day)** and **VIIRS VNP21 (1 km)** at coincident clear-sky times; the four MODIS+VIIRS overpasses constrain INSAT's diurnal curve.
- **Cloud-gap filling for LST:** where IR sensors see cloud, substitute **ERA5-Land skin temperature** and **SMAP L4 soil temperature**; reconstruct under-cloud LST with a diurnal-temperature-cycle (DTC) model fit to clear INSAT pixels, regularized by ERA5-Land.
- **Fine-scale downscaling:** sharpen INSAT/MODIS LST to **100 m (Landsat ST), 70 m (ECOSTRESS), or 10–30 m** using NDVI/albedo from Sentinel-2/Landsat (thermal-sharpening, e.g. DisTrad/TsHARP) for any city/field-scale pilot view.

### 11.3 Triple collocation (TC) — the rigorous cross-validation engine

TC estimates each dataset's random-error variance **without a perfect reference**, using three mutually independent products. For Indian monsoon rainfall, published TC setups use triplets like **{IMD gauge grid, IMERG/satellite, ERA5-Land/IMDAA reanalysis}** (and {IMD, CHIRPS, IMDAA}). Recommended for the PoC:

- **Rainfall TC triplet:** IMD-gauge ⟂ IMERG-satellite ⟂ ERA5-Land-reanalysis (three independent error structures).
- **LST/temperature TC triplet:** in-situ/IMD ⟂ MODIS-LST ⟂ ERA5-Land-skinT.
- **Soil-moisture TC triplet (well-established):** SMAP (passive) ⟂ ASCAT (active) ⟂ ERA5-Land/GLDAS (model) — ESA CCI SM was itself built on this principle.
- Use TC-derived error variances to set **fusion weights** and to produce a per-pixel **uncertainty field** for the digital twin (a twin without uncertainty is just a map).

### 11.4 Data assimilation / ML fusion options for the twin

- **Classical DA:** Optimal Interpolation / Ensemble Kalman Filter to nudge a background (ERA5/IMDAA) toward observations (IMD grid, IMERG, INSAT LST). Background-error covariances from the reanalysis ensemble spread.
- **ML/DL fusion:** train a spatiotemporal model (U-Net / ConvLSTM / Graph-NN / transformer) mapping multi-source stacks → bias-corrected, gap-filled state, with reanalysis as a physics-consistent prior. Indian ML benchmarks already exist to bootstrap: **BharatBench** and **IndiaWeatherBench** (both built on **IMDAA 12 km**) — reuse their train/test splits and baselines so results are comparable.
- **Short-term prediction (the "evolves" requirement):** seed a ConvLSTM/transformer nowcaster on the fused state + geostationary motion (INSAT/Himawari optical flow) for 0–6 h rainfall, and a residual-learning model on ERA5/IMDAA tendencies for 1–3 day temperature.

### 11.5 Independence matters

For valid cross-validation, prefer products with **independent error sources**: IMD (gauges) ⟂ IMERG (passive-MW+IR) ⟂ INSAT (IR-geo) ⟂ ERA5 (model+assimilation) ⟂ Himawari/Meteosat-IODC (independent geo). Avoid treating CHIRPS-v3-sat and IMERG as independent (CHIRPS v3 daily disaggregation *uses* IMERG-Late). Likewise ERA5-Land is **not** independent of ERA5.

---

## 12. PROGRAMMATIC ACCESS CHEAT-SHEET (fastest free routes)

> Below are minimal, copy-pasteable patterns for each major access channel. Asset IDs/buckets are the real ones cataloged above.

### 12.1 Google Earth Engine (Python) — broadest single window
```python
import ee; ee.Authenticate(); ee.Initialize(project="YOUR_GCP_PROJECT")
roi = ee.Geometry.Rectangle([72, 18, 80, 26])  # ~Maharashtra pilot box

era5_land = ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY").select("temperature_2m")
imerg     = ee.ImageCollection("NASA/GPM_L3/IMERG_V07").select("precipitation")
gsmap     = ee.ImageCollection("JAXA/GPM_L3/GSMaP/v7/operational").select("hourlyPrecipRate")
chirps    = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").select("precipitation")
mod11     = ee.ImageCollection("MODIS/061/MOD11A1").select("LST_Day_1km")
viirs_lst = ee.ImageCollection("NASA/VIIRS/002/VNP21A1D").select("LST_1KM")
smap_l4   = ee.ImageCollection("NASA/SMAP/SPL4SMGP/008").select("sm_surface")
s1        = ee.ImageCollection("COPERNICUS/S1_GRD")
grace     = ee.ImageCollection("NASA/GRACE/MASS_GRIDS_V04/MASCON").select("lwe_thickness")
```
GEE is the single fastest way to co-grid IMERG + ERA5-Land + MODIS LST + SMAP over a pilot box.

### 12.2 ERA5 / ERA5-Land via Copernicus CDS (`cdsapi`)
```python
# pip install cdsapi ; create ~/.cdsapirc with the CDS-Beta url + your API key
import cdsapi
cdsapi.Client().retrieve("reanalysis-era5-land",
  {"variable": ["2m_temperature", "total_precipitation"],
   "year":"2024","month":"07","day":[f"{d:02d}" for d in range(1,32)],
   "time":[f"{h:02d}:00" for h in range(24)],
   "area":[26,72,18,80],  # N,W,S,E  pilot box
   "format":"netcdf"}, "era5land_pilot.nc")
```

### 12.3 NASA data via `earthaccess` (IMERG, SMAP, MODIS, GRACE, AIRS, GLDAS, MERRA-2)
```python
# pip install earthaccess ; needs a free NASA Earthdata Login
import earthaccess; earthaccess.login()
res = earthaccess.search_data(short_name="GPM_3IMERGHHE", version="07",
        temporal=("2024-07-01","2024-07-31"), bounding_box=(72,18,80,26))
files = earthaccess.download(res, "./imerg_early")   # or earthaccess.open(res) to stream
```
Swap `short_name` for: `SPL4SMGP` (SMAP L4), `SPL3SMP_E` (SMAP L3), `MOD11A1`/`MYD11A1` (MODIS LST), `AIRS3STD` (AIRS L3), `GLDAS_NOAH025_3H`, `M2T1NXSLV` (MERRA-2), `TELLUS_GRAC-GRFO_MASCON_GRID_RL06.3_V4` (GRACE-FO).

### 12.4 Microsoft Planetary Computer (STAC) — Landsat ST, Sentinel-1/2/3, ECOSTRESS
```python
# pip install pystac-client planetary-computer
import planetary_computer, pystac_client
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace)
items = cat.search(collections=["landsat-c2-l2"],
        bbox=[72,18,80,26], datetime="2024-07-01/2024-07-31",
        query={"eo:cloud_cover":{"lt":20}}).item_collection()
# Each item asset (e.g. 'lwir11' / ST band) is a signed COG URL -> open with rioxarray/stackstac
```
Other MPC collections: `sentinel-2-l2a`, `sentinel-1-rtc`, `sentinel-3-slstr-lst-l2-netcdf`, `hls2-l30`.

### 12.5 AWS anonymous S3 (geostationary + Landsat + IMERG)
```bash
# Himawari-9 full disk (no credentials):
aws s3 ls --no-sign-request s3://noaa-himawari9/AHI-L1b-FLDK/
# GOES / global mosaic / Landsat:
aws s3 ls --no-sign-request s3://noaa-goes18/
aws s3 ls --no-sign-request s3://noaa-gmgsi/
aws s3 ls --no-sign-request s3://usgs-landsat/collection02/   # some prefixes RequesterPays
```
```python
import s3fs; fs = s3fs.S3FileSystem(anon=True)
fs.ls("noaa-himawari9/AHI-L1b-FLDK/2024/07/01/")
```

### 12.6 IMD gridded data via IMDLIB (mandated rainfall/temp Bin files)
```python
# pip install imdlib
import imdlib as imd
rain = imd.get_data("rain", 2015, 2024, fn_format="yearwise")   # 0.25 deg rainfall
tmax = imd.get_data("tmax", 2015, 2024, fn_format="yearwise")   # 1.0 deg max temp
ds = rain.get_xarray()           # -> xarray.Dataset
ds.to_netcdf("imd_rain.nc")      # or rain.to_geotiff(...) via rioxarray
```
This reads the IMD `.GRD` binary directly — no manual byte parsing.

### 12.7 MOSDAC (INSAT-3D LST/SST/IMC, Megha-Tropiques, Oceansat, SCATSAT)
- Register: `mosdac.gov.in/signup/` (approval required).
- Automated downloads: **MOSDAC Data Download API** driven by `config.json` (credentials + product code like `3RIMG_L2B_LST` + date range). Manual: `mosdac.gov.in/downloadapi-manual`; spec PDF at `mosdac.gov.in/sites/default/files/docs/MOSDAC_Satellite_Data_Download_API.pdf`.
- Open derived products (no order): `mosdac.gov.in/open-data`.
- HDF5 products → read with `h5py` / `xarray` (engine `h5netcdf`).

### 12.8 IMDAA regional reanalysis & Bhuvan OGC services
- **IMDAA:** register at NCMRWF RDS `rds.ncmrwf.gov.in`; download NetCDF/GRIB (hourly, 12 km). Heavy (TBs) — subset by variable/region.
- **Bhuvan:** OGC endpoints (WMS/WMTS/WCS/WFS/CSW) at `bhuvan.nrsc.gov.in`; load directly in QGIS ("Bhuvan Web Services" plugin) or via `owslib` in Python; Bhuvan REST APIs for Search/Statistics.

### 12.9 Other quick channels
- **CHIRPS:** GEE (fastest) or direct GeoTIFF/NetCDF from `chc.ucsb.edu/data/chirps3` / UCSB FTP.
- **GSMaP:** JAXA G-Portal (`gportal.jaxa.jp`) or GEE.
- **NCEP/NCAR:** NOAA PSL OPeNDAP `psl.noaa.gov/data/reanalysis/`.
- **ESA CCI Soil Moisture:** CEDA archive (registration) or CDS.
- **MSWEP:** request access at `gloh2o.org/mswep` (Google-Drive delivery).

---

## 13. PILOT-REGION DATA AVAILABILITY (choosing & covering an Indian pilot)

**Recommended pilot candidates** (pick one for the PoC):
- **Maharashtra / Krishna-Bhima basin** (~72–80E, 16–22N): strong gauge density (IMD performs best in peninsular India), mix of orographic Western Ghats + rain-shadow interior → good test of multi-source fusion gradients.
- **Indo-Gangetic Plain (Uttar Pradesh/Bihar)**: dense AWS, agriculture, monsoon core — good for temperature + rainfall extremes.
- **A single hydrological basin** so India-WRIS streamflow gives an independent water-balance check.

**Coverage matrix for any India pilot box:**

| Need | Coverage over India pilot | Best pick |
|---|---|---|
| Gauge truth (rain) | Dense, esp. peninsular | **IMD 0.25° grid** + IMD AWS |
| Gauge truth (temp) | Coarse (1.0°) | **IMD Tmax/Tmin** + IMD AWS for downscaling |
| Gap-free 2 m T | Full | **ERA5-Land (9 km)**, **IMDAA (12 km)** |
| NRT rainfall (30-min) | Full | **IMERG Early (0.1°)** + **INSAT IMC** + **GSMaP** |
| Fine LST (1 km, 4×/day) | Full (cloud-limited in monsoon) | **MODIS MOD11/MYD11** + **VIIRS VNP21** |
| High-cadence LST (30-min) | Full | **INSAT-3D/3DR/3DS LST (4 km)** |
| Very-fine LST (70–100 m) | Full but sparse revisit | **ECOSTRESS (70 m)**, **Landsat ST (100 m)** |
| Independent geostationary | India is at **edge of Himawari**, but **fully in Meteosat-IODC (45.5°E)** and **FengYun-4** | **Meteosat IODC** + **FengYun-4** (+ INSAT) |
| Soil moisture (9 km) | Full | **SMAP L3/L4** + **ASCAT** + **ESA CCI SM** |
| All-weather flood/SM (10 m) | Full | **Sentinel-1 GRD** |
| Water storage | Full (coarse) | **GRACE-FO mascon** |
| Land cover / NDVI covariate | Full | **Sentinel-2**, **Landsat**, **Bhuvan/NICES** |
| Hydrology truth | Full (basins) | **India-WRIS** |

**Monsoon caveat:** during JJAS, optical/IR LST (MODIS/VIIRS/INSAT) suffers heavy cloud loss over India — this is exactly why the strategy leans on **microwave rainfall (IMERG/GSMaP/SMAP)**, **reanalysis fill (ERA5-Land/IMDAA)**, and **DTC-based cloud-gap reconstruction**. Plan the twin's LST product as a *fused/reconstructed* field, never a single-sensor field.

**Geostationary note for India:** Himawari-8/9 (140.7E) only grazes the eastern edge of India; for an independent geostationary cross-check over the *whole* subcontinent prefer **Meteosat IODC (45.5°E)** and **FengYun-4** in addition to India's own INSAT-3D/3DR/3DS.

---

## 14. SOURCE-COUNT LEDGER (mandate: ≥30)

Indian (15+): INSAT-3D, INSAT-3DR, INSAT-3DS (imager+sounder+LST+SST+IMC), Oceansat-3 (OCM-3/OSCAT-3/SSTM), Oceansat-2, SCATSAT-1, Megha-Tropiques (SAPHIR/MADRAS/ScaRaB), RISAT, Cartosat, EOS-04/08, IMD gridded rainfall, IMD Tmax, IMD Tmin, IMD AWS, IMDAA, Bhuvan, NICES, India-WRIS, MOSDAC value-added.
Global reanalysis (8): ERA5, ERA5-Land, MERRA-2, NCEP/NCAR, JRA-3Q, JRA-55, GLDAS, FLDAS.
Global precip (8): GPM IMERG, TRMM/TMPA, GSMaP, CHIRPS, CMORPH, PERSIANN(-CDR/PDIR/CCS), MSWEP.
Global temp/LST (10): MODIS MOD11/MYD11, MOD21, VIIRS VNP21, AIRS L3, Landsat 8/9 ST, ECOSTRESS, Sentinel-3 SLSTR, OISST.
Optical (5): Sentinel-2, Landsat OLI, MODIS NDVI, Sentinel-3 OLCI, HLS.
SAR/soil moisture (6): SMAP L3, SMAP L4, Sentinel-1, ASCAT, ESA CCI SM, SMOS.
Gravity (1): GRACE/GRACE-FO. Geostationary (5): Himawari-8/9, Meteosat MSG/MTG-IODC, GOES, FengYun-4, GMGSI. Composition (1): Sentinel-5P. Hydrology/land (3): GLEAM, MOD16/PML ET, India-WRIS.
**Total distinct missions/datasets cataloged: 40+** ✔

---

## 15. KEY SOURCES (selected, 2023–2026 prioritized)

- MOSDAC INSAT-3D data products & Data Download API: `mosdac.gov.in/insat-3d-data-products`, `mosdac.gov.in/downloadapi-manual`, product DOI `mosdac.gov.in/doi/190/`
- INSAT-3DS (eoPortal / Wikipedia / MOSDAC payloads): `eoportal.org/satellite-missions/insat-3d`
- IMD gridded data: `imdpune.gov.in/cmpg/Griddata/` ; IMDLIB: `imdlib.readthedocs.io`, GitHub `iamsaswata/imdlib`
- ERA5 / ERA5-Land (CDS): `cds.climate.copernicus.eu/datasets/reanalysis-era5-land`; GEE `developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_HOURLY`
- GPM IMERG V07 (GES DISC / AWS): `earthdata.nasa.gov`, `registry.opendata.aws/nasa-gpm3imerghhl`
- GSMaP (JAXA/GEE): `sharaku.eorc.jaxa.jp/GSMaP`; CHIRPS: `chc.ucsb.edu/data/chirps3`
- MODIS/VIIRS LST (GEE/LP DAAC): `MODIS/061/MOD11A1`, `NASA/VIIRS/002/VNP21A1D`
- SMAP (NSIDC/GEE): `NASA/SMAP/SPL4SMGP/008`; GRACE-FO (PO.DAAC): `TELLUS_GRAC-GRFO_MASCON_GRID_RL06.3_V4`
- Landsat/Sentinel-3 (MPC): `planetarycomputer.microsoft.com/dataset/landsat-c2-l2`, `…/sentinel-3-slstr-lst-l2-netcdf`
- Himawari/GOES/GMGSI (AWS): `registry.opendata.aws/noaa-himawari`, `…/noaa-gmgsi`
- ESA CCI Soil Moisture: `climate.esa.int/en/projects/soil-moisture`; ASCAT/H SAF (EUMETSAT)
- IMDAA (NCMRWF): `rds.ncmrwf.gov.in`; J. Climate 2021 "IMDAA: High-Resolution Satellite-Era Reanalysis"
- Triple collocation over India (J. Hydrology 2025; ScienceDirect S0022169425004743); INSAT+IMERG+GSMaP 4 km fusion; MSWEP v3 `gloh2o.org/mswep`
- ML benchmarks on IMDAA: **BharatBench** (arXiv 2405.07534), **IndiaWeatherBench** (arXiv 2509.00653)
- Bhuvan OGC/APIs: `bhuvan.nrsc.gov.in`; India-WRIS: `indiawris.gov.in`; Sentinel-5P (GEE `COPERNICUS/S5P`)

> **Verification note:** MOSDAC product detail pages render client-side (JS), so exact per-product fields were confirmed via search snippets + format docs rather than live HTML scrape. INSAT-3D LST/SST/IMC = 4 km / 30-min HDF5 is consistent across MOSDAC product listing, the INSAT-3D Products format doc, and peer-reviewed validation papers. Resolutions/asset IDs for GEE/CDS/NASA were confirmed against the official catalog pages cited above.
