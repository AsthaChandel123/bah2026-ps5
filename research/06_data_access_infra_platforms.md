# 06 — Data Access, Ingestion & Deployment Platforms (BAH 2026 PS5)

**Project:** ISRO BAH 2026 PS5 — "AI-Powered Digital Twin of India's Climate"
**Scope of this doc:** Hands-on, implementation-ready guidance for (1) parsing IMD gridded `_Bin` data, (2) MOSDAC/INSAT access, (3) Bhuvan/NICES/India-WRIS, (4) fast global programmatic data platforms (GEE/CDS/Earthdata/Planetary Computer/AWS Open Data), (5) deployment/hosting for a FAST app, (6) pilot-region recommendation, (7) auth/friction realism + a robust ingestion plan.
**Last researched:** 2026-06-21. All code is copy-paste oriented. Verify version pins at build time.

> **TL;DR strategy:** Honor the mandated Indian sources (IMD `_Bin` via `imdlib`/direct numpy; MOSDAC INSAT via `mdapi.py`; Bhuvan/NICES/WRIS via OGC/WMS) for the "official India" layer, but build the bulk of the FAST, instant-programmatic ingestion on **Google Earth Engine + Copernicus CDS + AWS Open Data (anonymous S3)**, which mirror/cross-validate the same physical variables with zero manual ordering. Precompute everything to **Cloud-Optimized GeoTIFF (COG) + PMTiles + Zarr**, serve from **Cloudflare R2 (zero egress) behind Workers/Pages** for O(1)-feeling edge delivery.

---

## 0. Quick-reference cheat sheet

| Source | What | Access method | Auth friction | Format | Speed |
|---|---|---|---|---|---|
| **IMD Griddata** (imdpune.gov.in) | Daily rainfall 0.25°, Tmax/Tmin 1.0° | `imdlib` (`pip install imdlib`) or direct `numpy.fromfile` | None (public download page) | Fortran binary `.grd` → NetCDF | Medium (scrape/download) |
| **MOSDAC** (mosdac.gov.in) | INSAT-3D/3DR L1B/L2B (LST/SST/cloud) | `mdapi.py` + `config.json` | **Account + approval required**; 3-fail lockout; 5000 files/day | HDF5 | Slow (order/auth) |
| **Bhuvan** (nrsc.gov.in) | Thematic/admin layers, LULC | OGC WMS/WFS/WCS/WMTS + Bhuvan API token | API key for some endpoints | WMS/GeoTIFF/KML | Medium |
| **Bhoonidhi** (bhoonidhi.nrsc.gov.in) | NRSC satellite archive (Resourcesat, Oceansat, etc.) | Bhoonidhi API | Account | GeoTIFF/HDF | Medium |
| **India-WRIS** (indiawris.gov.in) | Hydrology/rainfall/groundwater | REST/WebGIS services | Mostly open | JSON/WMS | Medium |
| **Google Earth Engine** | IMERG, ERA5/ERA5-Land, MODIS LST, CHIRPS, Sentinel | Python `ee` API | Google acct + 1-time project reg (free, instant) | Server-side; export COG/Zarr | **Fast** |
| **Copernicus CDS** | ERA5, ERA5-Land (reanalysis) | `cdsapi` + `~/.cdsapirc` token | Free acct + token (instant) | NetCDF/GRIB | Medium (queue) |
| **NASA Earthdata** | GPM IMERG, MODIS, VIIRS | `earthaccess` + `.netrc` | Free Earthdata Login (instant) | HDF5/NetCDF/COG | Fast |
| **Microsoft Planetary Computer** | Sentinel-1/2, Landsat, etc. | `pystac-client` + `planetary-computer` | **No account** (anon STAC + signed URLs) | COG via STAC | **Fast** |
| **AWS Open Data** | ERA5 (NCAR), Sentinel-2 COGs, NOAA GFS, MODIS | Anonymous S3 (`--no-sign-request`) | **None** | NetCDF/Zarr/COG | **Fastest** |

---

## 1. IMD gridded `_Bin` format — what it is and how to parse it

### 1.1 What these files actually are
IMD's "Griddata" products are **Fortran-written unformatted, direct-access binary files** (`.grd` / `.GRD`). Each file holds one **year** of **daily** gridded values. Every "record" = one day = a full 2-D lat×lon grid of 4-byte (single-precision, little-endian) IEEE floats laid out **South→North** then West→East. There is **no header** in the direct-access variant — the file is a raw stream of `days × nlat × nlon` float32 values. Missing/no-data is flagged (commonly `-999.0` / `99.9` depending on product; check per-file).

Source pages (imdpune.gov.in/cmpg/Griddata):
- Rainfall 0.25° binary: https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html
- Rainfall 0.25° NetCDF: https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html
- Rainfall 1.0° NetCDF: https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_1_NetCDF.html
- Max Temp 1.0° binary: https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html
- Min Temp 1.0° binary: https://www.imdpune.gov.in/cmpg/Griddata/Min_1_Bin.html
- Merged satellite–gauge (GPM) rainfall 0.25°: https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF_Merged.html
- Group landing page: https://www.imdpune.gov.in/Clim_Pred_LRF_New/Grided_Data_Download.html

### 1.2 Exact grid specs (CONFIRMED from IMD pages)

**Rainfall — 0.25° × 0.25°**
- Grid: **135 (lon) × 129 (lat)** = 17,415 points per day.
- First record value at **6.5°N, 66.5°E**; second at 6.5°N, 66.75°E (lon varies fastest); last at **38.5°N, 100.0°E**.
- Latitude axis: 6.5°N → 38.5°N (129 steps of 0.25°). Longitude axis: 66.5°E → 100.0°E (135 steps of 0.25°).
- Unit: **mm**. Coverage **1901–2024** (annual files; 2025 partial appears in dropdown).
- File naming: `ind<YEAR>_rfp25.grd` (e.g. `ind2024_rfp25.grd`). RECL = `135*129*4 = 69,660` bytes/day.
- Fortran on the page:
  ```fortran
  PARAMETER(ISIZ=135, JSIZ=129)
  DIMENSION RF(366,ISIZ,JSIZ)
  OPEN(7, FILE='ind1901_rfp25.GRD', FORM='UNFORMATTED',
 +     ACCESS='DIRECT', RECL=ISIZ*JSIZ*4, STATUS='OLD')
  READ(7, REC=IDAY) ((RF(IDAY,I,J), I=1,ISIZ), J=1,JSIZ)
  ```
  (I = longitude index 1..135, J = latitude index 1..129; J=1 → 6.5°N.)

> **Older rainfall product, 1.0° × 1.0°** uses a **35 (lon) × 33 (lat)** grid spanning ~66.5–100.5°E, 6.5–38.5°N. Prefer the 0.25° product for the digital twin; keep 1° only for very-long-period context.

**Maximum & Minimum (and Mean) Temperature — 1.0° × 1.0°**
- Grid: **31 (lon) × 31 (lat)** = 961 points/day. `ISIZ=31, JSIZ=31`, RECL = `31*31*4 = 3,844` bytes/day.
- Latitude axis: **7.5°N → 37.5°N** (31 steps of 1.0°). Longitude axis: **67.5°E → 97.5°E** (31 steps of 1.0°).
- First record at 7.5°N, 67.5°E; last at 37.5°N, 97.5°E.
- Unit: **°C**. Coverage **1951–2024**. (Note: 2008+ uses ~180 real-time stations → coarser station density.)
- File naming examples seen on pages: `Maxtemp_MaxT_<YEAR>.GRD` style / `MaxT_NEW1<YEAR>.GRD` (Tmax), `MEANT<YEAR>.GRD` (mean), `Mintemp_…` (Tmin). Naming has varied across releases — **discover the exact filename from the page's dropdown/control file rather than hard-coding.**

> ⚠️ **Resolution discrepancy to be aware of:** The official IMD pages serve **temperature at 1.0°** (31×31). The `imdlib` docs sometimes mention "Temperature at 0.5°" — that refers to a different/real-time product stream, not the long-period archive. For the archive, treat Tmax/Tmin as **1.0° (31×31)**. `imdlib` handles the correct grid internally per `variable`.

### 1.3 Parsing in Python — Method A: `imdlib` (recommended, least code)

`imdlib` (Saswata Nandi; MIT; PyPI `imdlib` v0.1.21 as of Dec 2025; paper: Environmental Modelling & Software 2024, doi:10.1016/j.envsoft.2023.105869). It **downloads** from IMD, reads `.grd` into an `xarray`-backed IMD object, and exports NetCDF/GeoTIFF/CSV. Repo: https://github.com/iamsaswata/imdlib • Docs: https://imdlib.readthedocs.io

```bash
pip install imdlib xarray netCDF4 rioxarray
```

```python
import imdlib as imd

# --- Download yearly archive data (rain=0.25°, tmin/tmax=1.0°) ---
start_yr, end_yr = 2000, 2024
rain = imd.get_data('rain', start_yr, end_yr, fn_format='yearwise', file_dir='./imd_data')
tmax = imd.get_data('tmax', start_yr, end_yr, fn_format='yearwise', file_dir='./imd_data')
tmin = imd.get_data('tmin', start_yr, end_yr, fn_format='yearwise', file_dir='./imd_data')
# file_dir gets sub-dirs: ./imd_data/rain, ./imd_data/tmin, ./imd_data/tmax

# --- Re-open already-downloaded data later (no re-download) ---
rain = imd.open_data('rain', start_yr, end_yr, 'yearwise', file_dir='./imd_data')

# --- Convert to xarray / NetCDF / GeoTIFF / point-CSV ---
ds = rain.get_xarray()                     # xarray.Dataset, dims (time, lat, lon)
rain.to_netcdf('imd_rain_2000_2024.nc', './out')
rain.to_geotiff('imd_rain.tif', './out')   # per-time GeoTIFF stack
rain.to_csv('pune_rain.csv', 18.52, 73.85, './out')  # point time series (lat, lon)

# --- Real-time daily product (recent days; rain 0.25°, temp 0.5°) ---
rt = imd.get_real_data('rain', '2026-06-01', '2026-06-20', file_dir='./imd_rt')
rt = imd.open_real_data('rain', '2026-06-01', '2026-06-20', file_dir='./imd_rt')

# --- Built-in climate analytics (huge time-saver for a "digital twin") ---
clim   = rain.climatology()                       # long-term mean
anom   = rain.anomaly()                            # anomaly vs climatology
heavy  = rain.compute('d64', 'A', threshold=64.5)  # heavy-rain days/yr (>64.5 mm)
cdd    = rain.compute('cdd', 'A', threshold=2.5)   # consecutive dry days
spi3   = rain.compute('spi', 'M', timescale=3)     # 3-month SPI (drought)
spei3  = rain.compute('spei','M', timescale=3, tmax=tmax, tmin=tmin)
hw     = tmax.heatwave(output='annual')            # heat-wave detection
ts     = rain.spatial_mean()                       # area-mean pandas series
```

> `imdlib` performs the download from the IMD server internally (the `cmpg/Griddata` endpoints). If a network/scrape change breaks `get_data`, fall back to manual download + Method B.

### 1.4 Parsing in Python — Method B: direct `numpy.fromfile` (robust, dependency-light)

Use this when you already have the `.grd` file (downloaded manually or via `imdlib`) and want full control, or when `imdlib`'s scraper breaks. This mirrors the Fortran/R `readBin` approach.

```python
import numpy as np
import xarray as xr
import pandas as pd

def read_imd_grd(path, year, var='rain'):
    """Read an IMD yearly .grd into an xarray.DataArray (time, lat, lon)."""
    if var == 'rain':                         # 0.25° rainfall
        nlon, nlat = 135, 129
        lon = np.linspace(66.5, 100.0, nlon)  # 0.25° steps
        lat = np.linspace(6.5,  38.5,  nlat)
        undef = -999.0
    else:                                      # tmax / tmin / tmean, 1.0°
        nlon, nlat = 31, 31
        lon = np.linspace(67.5, 97.5, nlon)
        lat = np.linspace(7.5,  37.5, nlat)
        undef = 99.9                           # verify per product/page

    ndays = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    raw = np.fromfile(path, dtype='<f4')       # little-endian float32, no header
    expected = ndays * nlat * nlon
    if raw.size != expected:                    # some years are off-by-leap; trim/pad
        ndays = raw.size // (nlat * nlon)
        raw = raw[:ndays * nlat * nlon]
    # Fortran lays lon fastest, then lat (S->N), then day -> shape (day, lat, lon)
    arr = raw.reshape(ndays, nlat, nlon)
    arr = np.where(arr == undef, np.nan, arr)

    time = pd.date_range(f'{year}-01-01', periods=ndays, freq='D')
    da = xr.DataArray(arr, dims=('time', 'lat', 'lon'),
                      coords={'time': time, 'lat': lat, 'lon': lon},
                      name=var, attrs={'units': 'mm' if var == 'rain' else 'degC'})
    return da

rain2024 = read_imd_grd('ind2024_rfp25.grd', 2024, var='rain')
rain2024.to_netcdf('imd_rain_2024.nc')
```

### 1.5 Convert to NetCDF / Zarr / COG (for the digital twin pipeline)

```python
import xarray as xr, rioxarray  # noqa
ds = xr.open_mfdataset('imd_data/rain/*.nc', combine='by_coords')  # multi-year

# --- Zarr (chunked, cloud-native; great for time-series scrubbing) ---
ds.chunk({'time': 365, 'lat': -1, 'lon': -1}).to_zarr('imd_rain.zarr', mode='w')

# --- COG per timestep (for map tiles / web rendering) ---
da = ds['rain'].isel(time=0)
da = da.rio.write_crs('EPSG:4326')
da.rio.to_raster('imd_rain_20240101_cog.tif', driver='COG',
                 compress='DEFLATE', BLOCKSIZE=512, overview_resampling='average')
```
> Then turn COG/vector layers into **PMTiles** (single-file tile pyramid) for cheap edge serving — see §5.

### 1.6 No-Python escape hatch
- **IRI Data Library** mirrors IMD RF0p25 daily as NetCDF/OPeNDAP: https://iridl.ldeo.columbia.edu/SOURCES/.IMD/.RF0p25/ — instant programmatic subsetting without scraping IMD.
- IMD also offers ready **NetCDF** versions on the same Griddata pages (skip binary parsing entirely if you only need recent product, but the file is still gated behind the dropdown form).

---

## 2. MOSDAC access — INSAT-3D/3DR L2B (LST / SST / cloud)

### 2.1 Registration & auth (REALISM: this is the highest-friction mandated source)
- **Account required** for the mandated L2B products. Sign up: https://mosdac.gov.in/signup/ → wait for **approval** (manual, can take hours–days).
- Anonymous users can download **only "open data"** (a limited subset). Most L2B science products require login.
- **3 consecutive failed logins → temporary lockout.** **Daily cap: 5000 files/user.**
- Product/format docs:
  - Download API manual: https://www.mosdac.gov.in/downloadapi-manual
  - Catalog (find exact `datasetId`): https://mosdac.gov.in/catalog-app/satellite.php
  - INSAT-3D products: https://www.mosdac.gov.in/insat-3d-data-products
  - 3RIMG_L2B_LST DOI page: https://mosdac.gov.in/doi/190/
  - Product format doc (HDF5 layout): https://www.mosdac.gov.in/docs/INSAT3D_Products.pdf
  - Product version info: https://www.mosdac.gov.in/sites/default/files/docs/INSAT_Product_Version_information_V01.pdf

### 2.2 Products & format
- **Format: HDF5** for all INSAT-3D/3DR L1B/L2B/L3 products (Standard + Geophysical Parameters in HDF5). Read with `h5py` / `xarray` (`engine='h5netcdf'` may work; otherwise `h5py`).
- Mandated datasetIds (Imager / "3RIMG"):
  - `3RIMG_L2B_LST` — Land Surface Temperature.
  - `3RIMG_L2B_SST` — Sea Surface Temperature (4 km, half-hourly cadence noted on catalog).
  - `3RIMG_L2B_IMC` — Imager cloud product (cloud mask / cloud properties). HDF5; half-hourly multispectral over the Indian disk.
  - (3DR variants exist with the `3RIMG` family from INSAT-3DR.)
- Typical Imager L2B resolution ≈ **4 km**, temporal **30 min** (geostationary full-disk over India).

### 2.3 Programmatic download via `mdapi.py`
```bash
# 1) Download the official client
wget https://www.mosdac.gov.in/software/mdapi.zip && unzip mdapi.zip
pip install requests tqdm
# 2) Edit config.json (below), then:
python mdapi.py            # prompts "Do you want to start downloading? (Y/N)"
```
`config.json` (from the official manual):
```json
{
  "user_credentials": {
    "username": "your_username",
    "password": "your_password"
  },
  "search_parameters": {
    "datasetId": "3RIMG_L2B_LST",
    "startTime": "2024-06-01",
    "endTime":   "2024-06-30",
    "count": "50",
    "boundingBox": "66.5,6.5,100.0,38.5",
    "gId": ""
  },
  "download_settings": {
    "download_path": "/home/user/mosdac_data",
    "organize_by_date": true,
    "skip_user_prompt": true,
    "generate_error_log": true,
    "error_log_path": "/home/user/mosdac_logs"
  }
}
```
Workflow the script runs: **search** (returns file counts/sizes) → **authenticate** → **download** → **logout**. `boundingBox` is `minLon,minLat,maxLon,maxLat`.

### 2.4 Reading an INSAT-3D L2B HDF5 in Python
```python
import h5py, numpy as np
with h5py.File('3RIMG_..._L2B_LST.h5', 'r') as f:
    def walk(g, p=''):
        for k in g:
            o = g[k]
            print(p + '/' + k, getattr(o, 'shape', ''), getattr(o, 'dtype', ''))
            if isinstance(o, h5py.Group): walk(o, p + '/' + k)
    walk(f)                                   # discover dataset names
    lst = f['LST'][:]                          # name varies; inspect first
    lat = f['Latitude'][:]; lon = f['Longitude'][:]
    lst = np.where(lst == f['LST'].attrs.get('_FillValue', -999), np.nan, lst)
```

### 2.5 Fallback if MOSDAC auth/order is too slow (it often is)
- **LST:** use **MODIS LST** (`MODIS/061/MOD11A1` / `MYD11A1`) on GEE or Earthdata — instant, validated, daily 1 km.
- **SST:** use **NOAA/MUR SST** or MODIS SST on AWS/Earthdata.
- **Cloud:** use **IMERG**/Sentinel cloud or ERA5 cloud cover.
Keep MOSDAC as the "official INSAT" badge layer; cross-validate against the instant global mirrors for the actual modeling.

---

## 3. Bhuvan / NICES / India-WRIS / Bhoonidhi

### 3.1 Bhuvan (NRSC/ISRO geoportal)
- **OGC services:** WMS (raster/vector maps), **WFS** (vector query), **WCS** (raster coverage), **WMTS** (tiles), CSW (metadata), WPS, SOS, plus KML. This is the most "web-app friendly" Indian source — you can pull layers straight into Leaflet/MapLibre/OpenLayers as WMS/WMTS without downloading rasters.
- **Bhuvan API** (themes/resources, some need a token): https://bhuvan-app1.nrsc.gov.in/api/
- Geoportal: https://bhuvan.nrsc.gov.in/ngmaps
- Typical usable layers: LULC, admin boundaries, NDVI/thematic, disaster layers. Great for the basemap/overlay and admin-boundary joins in the twin.

Example (MapLibre/Leaflet WMS tile URL pattern — confirm exact layer names from GetCapabilities):
```
https://bhuvan-vec1.nrsc.gov.in/bhuvan/wms?service=WMS&version=1.1.1&request=GetMap
&layers=<LAYER_NAME>&bbox={bbox}&width=256&height=256&srs=EPSG:3857
&format=image/png&transparent=true
```
Always start from `...?service=WMS&request=GetCapabilities` to enumerate layers.

### 3.2 Bhoonidhi (NRSC satellite data archive — Resourcesat, Oceansat, Cartosat, etc.)
- API spec: https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/ — supports programmatic search/order/download of NRSC EO archive (account required). This is the route for **Oceansat** (OCM/scatterometer) products mandated by PS5.

### 3.3 NICES (National Information System for Climate and Environment Studies)
- ISRO/NRSC programme delivering long-term ECV (Essential Climate Variable) geophysical products (e.g., AOD, vegetation, radiation, soil moisture). Distributed via Bhuvan/MOSDAC portals; discover datasets through the Bhuvan NICES section and MOSDAC catalog. Treat as curated value-added layers; access mirrors Bhuvan/MOSDAC (OGC + account-gated downloads).

### 3.4 India-WRIS (Water Resources Information System)
- https://indiawris.gov.in — single-window hydrology: rainfall, river discharge, groundwater levels, reservoir storage, soil moisture. Exposes **WebGIS + REST services** (mostly open). Useful for ground-truth hydrology and drought/flood layers in the twin. Pull station/series JSON from its data services and the WMS layers for spatial context.

> **Bottom line for §3:** For a *fast web app*, prefer Bhuvan/India-WRIS **WMS/WMTS** (render directly, no storage) for overlays and India-WRIS REST for hydrology series; reserve Bhoonidhi/MOSDAC downloads for offline precompute.

---

## 4. Global easy-access platforms (fast/free programmatic paths)

These fill gaps, cross-validate the Indian sources, and are usually the **fastest** route to a working pipeline.

### 4.1 Google Earth Engine (Python `ee`) — best for server-side compute + export
One-time: create a free Cloud project, enable Earth Engine, `earthengine authenticate`.
```bash
pip install earthengine-api geemap
```
```python
import ee
ee.Authenticate()                       # one-time
ee.Initialize(project='YOUR_GCP_PROJECT')

india = ee.Geometry.Rectangle([66.5, 6.5, 100.0, 38.5])

# --- Precipitation: GPM IMERG V07 (0.1°, 30-min) and CHIRPS daily ---
imerg  = ee.ImageCollection('NASA/GPM_L3/IMERG_V07').select('precipitation')  # mm/hr
chirps = ee.ImageCollection('UCSB-CHC/CHIRPS/DAILY').select('precipitation')   # mm/day (V2)
# CHIRPS V3: 'UCSB-CHC/CHIRPS/V3/DAILY_SAT' (IMERG-based NRT), '.../DAILY_RNL' (ERA5 reanalysis)

# --- Reanalysis: ERA5-Land daily/hourly + ERA5 hourly ---
era5l_day = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR')   # temperature_2m (K), total_precipitation_sum (m)
era5l_hr  = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY')
era5_hr   = ee.ImageCollection('ECMWF/ERA5/HOURLY')            # total_precipitation, temperature_2m

# --- LST: MODIS Terra/Aqua daily 1 km (LST_Day_1km is in 0.02 K; scale ×0.02, −273.15 for °C) ---
modis_lst = ee.ImageCollection('MODIS/061/MOD11A1').select('LST_Day_1km')

# Example: monsoon (JJAS) 2024 total rainfall over India from IMERG
jjas = imerg.filterDate('2024-06-01', '2024-10-01').filterBounds(india)
rain_mm = jjas.sum().multiply(0.5)      # 30-min mm/hr -> mm per slot (×0.5h); sum over season
task = ee.batch.Export.image.toCloudStorage(
    image=rain_mm.clip(india), description='imerg_jjas2024',
    bucket='YOUR_GCS_BUCKET', fileNamePrefix='imerg_jjas2024',
    region=india, scale=11132, fileFormat='GeoTIFF',
    formatOptions={'cloudOptimized': True})   # -> COG directly
task.start()
```
Key asset IDs (verified):
- IMERG half-hourly V07: `NASA/GPM_L3/IMERG_V07` (band `precipitation`, mm/hr; also `MWprecipitation`, `IRprecipitation`). Monthly: `NASA/GPM_L3/IMERG_MONTHLY_V07`.
- ERA5-Land daily: `ECMWF/ERA5_LAND/DAILY_AGGR`; hourly: `ECMWF/ERA5_LAND/HOURLY`; monthly: `ECMWF/ERA5_LAND/MONTHLY_AGGR`.
- ERA5 hourly: `ECMWF/ERA5/HOURLY`; ERA5 daily: `ECMWF/ERA5/DAILY`.
- MODIS LST: `MODIS/061/MOD11A1` (Terra), `MODIS/061/MYD11A1` (Aqua); newer LST&E: `MODIS/061/MOD21C1`.
- CHIRPS: `UCSB-CHC/CHIRPS/DAILY` (V2), `UCSB-CHC/CHIRPS/V3/DAILY_SAT`, `UCSB-CHC/CHIRPS/V3/DAILY_RNL`.

### 4.2 Copernicus Climate Data Store — `cdsapi` (ERA5 / ERA5-Land)
Setup `~/.cdsapirc` (token from https://cds.climate.copernicus.eu/how-to-api after free signup; **accept each dataset's licence once**):
```
url: https://cds.climate.copernicus.eu/api
key: <YOUR-API-TOKEN>
```
```bash
pip install cdsapi xarray netCDF4
```
```python
import cdsapi
c = cdsapi.Client()

# ERA5-Land hourly 2m temperature + total precipitation over India, June 2024 -> NetCDF
c.retrieve('reanalysis-era5-land', {
    'variable': ['2m_temperature', 'total_precipitation'],
    'year': '2024', 'month': '06',
    'day':  [f'{d:02d}' for d in range(1, 31)],
    'time': [f'{h:02d}:00' for h in range(24)],
    'area': [38.5, 66.5, 6.5, 100.0],     # N, W, S, E
    'data_format': 'netcdf',
    'download_format': 'unarchived',
}, 'era5land_india_202406.nc')

# ERA5 single-levels monthly means (lighter for climatology)
c.retrieve('reanalysis-era5-single-levels-monthly-means', {
    'product_type': 'monthly_averaged_reanalysis',
    'variable': ['2m_temperature', 'total_precipitation'],
    'year': [str(y) for y in range(1991, 2021)], 'month': [f'{m:02d}' for m in range(1,13)],
    'time': '00:00', 'area': [38.5, 66.5, 6.5, 100.0],
    'data_format': 'netcdf', 'download_format': 'unarchived',
}, 'era5_clim_1991_2020.nc')
```
> Requests **queue** (minutes→hours for big pulls). For instant ERA5, use the AWS NCAR mirror (§4.5) or GEE.

### 4.3 NASA Earthdata — `earthaccess` (GPM IMERG, MODIS, VIIRS)
```bash
pip install earthaccess xarray h5netcdf
```
Auth via `.netrc` (host `urs.earthdata.nasa.gov`) or interactive:
```python
import earthaccess
auth = earthaccess.login(strategy='netrc')   # or strategy='interactive' (writes .netrc)

results = earthaccess.search_data(
    short_name='GPM_3IMERGDF',                 # IMERG Final daily V07 (DOI 10.5067/GPM/IMERGDF/DAY/07)
    temporal=('2024-06-01', '2024-09-30'),
    bounding_box=(66.5, 6.5, 100.0, 38.5))     # (W, S, E, N)
files = earthaccess.download(results, './imerg_daily')

import xarray as xr
ds = xr.open_mfdataset(files, group='Grid')    # IMERG HDF5 uses a 'Grid' group
```
Useful `short_name`s: `GPM_3IMERGDF` (daily), `GPM_3IMERGHH` (half-hourly), `GPM_3IMERGM` (monthly); MODIS LST `MOD11A1`/`MYD11A1`; supports cloud-hosted streaming via `earthaccess.open()` (no full download).

### 4.4 Microsoft Planetary Computer — `pystac-client` + `planetary-computer` (NO account)
```bash
pip install pystac-client planetary-computer odc-stac rioxarray
```
```python
import planetary_computer, pystac_client
cat = pystac_client.Client.open(
    'https://planetarycomputer.microsoft.com/api/stac/v1',
    modifier=planetary_computer.sign_inplace)   # auto-signs asset hrefs; no login

search = cat.search(
    collections=['sentinel-2-l2a'],
    bbox=[72.5, 18.8, 73.2, 19.3],              # Mumbai-ish
    datetime='2024-06-01/2024-06-30',
    query={'eo:cloud_cover': {'lt': 20}})
items = list(search.items())
href = items[0].assets['B04'].href              # signed COG URL, stream with rioxarray
import rioxarray; red = rioxarray.open_rasterio(href)
```
Collections of interest: `sentinel-2-l2a`, `sentinel-1-rtc`, `landsat-c2-l2`, `modis-11A2-061` (LST), `era5-pds`, `io-lulc-annual-v02`. STAC metadata is public; only asset bytes need signing (free).

### 4.5 AWS Open Data — anonymous S3 (the FASTEST, zero-auth path)
```bash
pip install s3fs boto3 xarray zarr rioxarray
```
```python
import s3fs, xarray as xr
fs = s3fs.S3FileSystem(anon=True)               # no credentials

# ERA5 (NSF NCAR rehost), us-west-2, NetCDF-4, hourly 0.25°
fs.ls('s3://nsf-ncar-era5/')                     # browse: e2/oper/an_sfc/<YYYYMM>/...
# (legacy 'era5-pds' in us-east-1 still exists but is deprecated)

# Sentinel-2 L2A Cloud-Optimized GeoTIFFs (public, us-west-2)
#   s3://sentinel-cogs/sentinel-s2-l2a-cogs/<UTM>/<lat-band>/<square>/<YYYY>/<M>/<scene>/B04.tif
red = '/vsis3/sentinel-cogs/sentinel-s2-l2a-cogs/43/Q/CA/2024/6/.../B04.tif'

# NOAA GFS (forecast), MODIS COGs (modis-pds / modis on AWS)
fs.ls('s3://noaa-gfs-bdp-pds/')
```
Anonymous CLI sanity check: `aws s3 ls --no-sign-request s3://nsf-ncar-era5/`.
Key buckets: `nsf-ncar-era5` (ERA5 NetCDF, us-west-2, anon), `era5-pds` (legacy Zarr/NetCDF, us-east-1), `sentinel-cogs` (Sentinel-2 L2A COGs, anon), `noaa-gfs-bdp-pds` (GFS), `modis-pds`/MODIS-on-AWS (COGs). Registry: https://registry.opendata.aws/.

---

## 5. Deployment / hosting for a FAST app

### 5.1 Recommended architecture (free-tier-friendly, edge-fast, "O(1)-feeling")
```
                         ┌─────────────────────────────────────────┐
   Offline precompute    │  GEE / CDS / Earthdata / AWS Open Data    │
   (Python, GitHub       │  + IMD imdlib + MOSDAC mdapi (badge data) │
    Actions / Modal)     └───────────────┬───────────────────────────┘
                                         │  COG + PMTiles + Zarr + JSON
                                         ▼
                         ┌─────────────────────────────────────────┐
                         │   Cloudflare R2  (object storage,        │
                         │   ZERO egress, S3-compatible)            │
                         └───────────────┬───────────────────────────┘
            tiles/COG/PMTiles ◄──────────┤ API/inference
                                         ▼
   ┌───────────────────────┐   ┌────────────────────────────────────┐
   │ Cloudflare Pages       │   │ Cloudflare Workers (edge API):     │
   │ (Next.js/MapLibre UI)  │◄──┤  - serve PMTiles ranges from R2    │
   │  global CDN            │   │  - KV cache, D1 for metadata       │
   └───────────────────────┘   └────────────────────────────────────┘
                                         │ heavy ML inference
                                         ▼
                         ┌─────────────────────────────────────────┐
                         │ HF Spaces (ZeroGPU) / Modal / Replicate  │
                         │  OR precompute predictions offline       │
                         └─────────────────────────────────────────┘
```
**Why this is fast:** static UI + tiles served from a global CDN (cache hit = edge latency); precomputed COG/PMTiles mean the "query" is a byte-range read, not a compute; R2 has **zero egress** so serving lots of map tiles is free; Workers run at the edge for sub-50 ms API.

### 5.2 Platform comparison (verified free-tier numbers, 2025–2026)

| Platform | Best for | Free tier (key limits) | Notes |
|---|---|---|---|
| **Cloudflare R2** | Object storage for COG/PMTiles/Zarr | **10 GB-month** storage, **1M Class-A** + **10M Class-B** ops/mo, **egress FREE** | Zero egress is the killer feature for tile/COG serving. S3-compatible API. |
| **Cloudflare Workers** | Edge API / tile range server | Free: ~**100k requests/day**; Paid $5/mo → **10M req/mo** + $0.30/extra M | Pair with R2 binding + KV cache. Sub-50 ms cold-ish starts (V8 isolates). |
| **Cloudflare Pages** | Static/Next.js frontend on CDN | Generous free (unlimited static requests, 500 builds/mo) | Best home for MapLibre/Leaflet UI; integrates with Workers + R2. |
| **Cloudflare KV / D1** | Edge cache / metadata SQL | Free tiers ample for metadata, station lists | D1 = serverless SQLite at edge; great for catalog/station indexes. |
| **Vercel (Hobby)** | Next.js frontend + serverless/edge fns | **100 GB bandwidth/mo**, **1M edge req/mo**, **100k function invocations/mo**, **4 CPU-hrs/mo**, 60 s timeout; **non-commercial only** | Best Next.js DX; but Hobby is personal-use and metered. Use Pro for commercial. |
| **Google Cloud Run** | Containerized Python API/inference | **2M requests/mo**, **180k vCPU-s**, **360k GiB-s** (us-central1/east1/west1) | Run heavy `xarray`/GDAL APIs as a container; scales to zero. |
| **Hugging Face Spaces** | ML demo (Gradio/Streamlit) + GPU | Free CPU Spaces; **ZeroGPU** (NVIDIA H200, ~70 GB VRAM, dynamic alloc, **Gradio only**); PRO $9/mo for more quota | Easiest public ML demo; ZeroGPU = free bursty GPU inference. Streamlit runs as Docker (no ZeroGPU). |
| **Modal** | Serverless GPU for custom inference/training | Pay-as-you-go (monthly free credits) | Best for custom PyTorch inference at scale; Python-native. |
| **Replicate** | Hosted model inference API | Pay-per-call | Good if a published model fits; also routed via HF Inference Providers. |
| **Render / Railway / Fly.io** | Always-on small services/DB | Limited free / hobby tiers | Fly.io = good for global edge containers; Render/Railway simpler for Postgres + web service. |

### 5.3 Concrete recommendation
**Primary: Cloudflare stack** — Pages (frontend) + Workers (edge API + PMTiles range server) + R2 (COG/PMTiles/Zarr) + KV/D1 (metadata). Rationale: **zero-egress object storage** + global edge make tile/COG delivery effectively O(1) and free, which is exactly the "FASTEST platform" mandate for a data-heavy map app.

**Secondary/complementary:**
- If the team prefers **Next.js DX**, host the frontend on **Vercel** and keep **R2 + Workers** for tiles/data (avoid Vercel egress costs on big tiles). Vercel Hobby is fine for the demo but is non-commercial.
- **Heavy Python geo-API** (on-the-fly xarray/GDAL, COG mosaicking) → **Google Cloud Run** (2M req/mo free, scales to zero) or a **TiTiler** instance.
- **ML inference / interactive demo** → **Hugging Face Spaces (Gradio + ZeroGPU)** for the public demo; **Modal** for serious custom inference; or **precompute predictions offline** and serve as static COG/JSON (fastest + cheapest — strongly recommended for the twin's forecast layers).

**Tile/format choices:** store **COG** for rasters (range-read, GDAL/TiTiler-native), **PMTiles** for vector/precomputed raster tile pyramids (single file on R2, served by a Worker), **Zarr** for time-series cubes (scrubbing through dates). Tools: `rio-cogeo`, `pmtiles`/`tippecanoe`, `titiler`, `xarray`+`zarr`.

---

## 6. Pilot-region recommendation

Pick regions with **strong, contrasting climate signals**, **good IMD station density**, and **societal relevance** (drought, extreme rain, heat). Recommend **two complementary pilots**, with a single primary if only one is feasible.

### Primary pilot — **Marathwada / central Maharashtra drought belt** ⭐
- **Why:** Quintessential Indian drought hotspot (Aurangabad/Beed/Latur/Osmanabad), strong monsoon **variability** and recurrent drought → showcases SPI/SPEI, dry-spell, and rainfall-anomaly modeling. Good IMD 0.25° rainfall + 1° temperature coverage; India-WRIS has rich reservoir/groundwater series here; clear policy story.
- **Bounding box (lon/lat):** **`[74.0, 17.5, 79.0, 21.0]`** (W, S, E, N) → roughly Marathwada + adjoining central Maharashtra. Tighter Marathwada core: `[75.0, 17.7, 78.5, 20.5]`.
- **Star variables:** IMD rainfall 0.25°, IMERG, CHIRPS, ERA5-Land soil moisture/temperature; derived SPI-3/SPI-6, consecutive dry days.

### Secondary pilot — **Kerala / Western Ghats heavy-rain & flood belt**
- **Why:** Among the wettest parts of India; orographic monsoon extremes, 2018/2019 flood relevance; strong daily-rainfall signal stresses the heavy-rain indices (>64.5 mm, >124.5 mm days) and validates IMERG/CHIRPS vs IMD gauges.
- **Bounding box:** **`[74.5, 8.0, 77.5, 13.0]`** (covers Kerala + Western Ghats crest; extend N to 13.0 for coastal Karnataka Ghats).

### Strong alternates (if a heat or basin-scale story is preferred)
- **Delhi-NCR heat/UHI:** `[76.5, 28.0, 77.8, 29.2]` — extreme heat waves, urban heat island, MODIS LST + IMD Tmax shine here.
- **Ganga basin (Bihar/UP) flood + heat corridor:** `[80.0, 24.0, 88.0, 28.5]` — basin-scale monsoon flooding + pre-monsoon heat; large signal, good for a "national twin" demo slice.

> **Recommendation:** Lead with **Marathwada** (drought, richest analytics story + data) and optionally add **Kerala/Western Ghats** (extreme rain) for contrast. Both have excellent IMD + global mirror coverage and clear extremes to model.

---

## 7. Auth/friction realism & robust ingestion plan

### 7.1 Friction map (instant vs gated)
- **Instant, zero-auth (build the backbone here):** AWS Open Data anonymous S3 (`nsf-ncar-era5`, `sentinel-cogs`, NOAA), Microsoft Planetary Computer (anon STAC + free signing), IRI Data Library (IMD mirror via OPeNDAP).
- **Instant after 1-time free signup:** Google Earth Engine (Google acct + project), Copernicus CDS (`cdsapi` token; per-dataset licence click), NASA Earthdata (`earthaccess`/`.netrc`). All scriptable thereafter.
- **Public download page, no login, but scrape/dropdown:** **IMD Griddata** (`imdlib` handles it; numpy fallback). Brittle to site changes → cache aggressively.
- **Account + approval + caps (highest friction):** **MOSDAC** (signup → approval; 3-fail lockout; 5000 files/day) and **Bhoonidhi** (NRSC archive; Oceansat). **Bhuvan/India-WRIS** mostly open via OGC/REST (some Bhuvan API endpoints need a token).

### 7.2 Robust ingestion plan (prefer instant global mirrors, still honor mandated sources)
1. **Mandated "official India" layer (badge + compliance):**
   - IMD rainfall 0.25° + Tmax/Tmin 1.0° via `imdlib` (Method A) → NetCDF/Zarr/COG. Cache the raw `.grd` in R2 so you never re-scrape.
   - MOSDAC `3RIMG_L2B_LST/SST/IMC` via `mdapi.py` **for a bounded sample window** (e.g., one monsoon season over the pilot bbox) — enough to demonstrate INSAT integration without fighting the 5000/day cap and approval lag.
   - Bhuvan WMS/WMTS overlays + India-WRIS hydrology REST rendered live (no storage).
2. **Fast global backbone (do the heavy lifting here):**
   - Precipitation: **IMERG** (GEE/Earthdata) + **CHIRPS** (GEE) — cross-validate against IMD rainfall.
   - Reanalysis (temperature, soil moisture, wind): **ERA5-Land** via **AWS `nsf-ncar-era5`** (instant) or GEE; CDS for specific variables.
   - LST: **MODIS MOD11A1/MYD11A1** (GEE/Earthdata) as the instant proxy/validation for MOSDAC INSAT LST.
   - Optical context: **Sentinel-2 COGs** (Planetary Computer / `sentinel-cogs`).
3. **Normalize & precompute (offline, GitHub Actions or Modal):**
   - Reproject to EPSG:4326, clip to pilot bbox, compute indices (SPI/SPEI, dry-spell, heat-wave, anomalies) with `imdlib`/`xclim`/`xarray`.
   - Emit **COG** (maps), **PMTiles** (tiles), **Zarr** (time cubes), **JSON** (station/series, summaries).
4. **Store & serve:** push artifacts to **R2**; serve via **Workers/Pages** (edge CDN). Cache catalog/metadata in **KV/D1**.
5. **Model inference:** precompute forecast/anomaly layers offline (fastest); expose an optional interactive demo on **HF Spaces (ZeroGPU)** or **Modal** for live inference.
6. **Resilience:** every mandated source has a global mirror fallback (IMD→IRI/IMERG; MOSDAC LST→MODIS; MOSDAC SST→NOAA MUR). If a gated source stalls, the app still renders from the instant backbone.

### 7.3 Risks & mitigations
- **IMD page/scraper changes** → cache raw `.grd` in R2; keep numpy reader (Method B) as fallback; IRI mirror as backup.
- **MOSDAC approval delay / caps** → start the account application Day 1; pull only a sample window; lean on MODIS/NOAA mirrors for modeling.
- **CDS queue latency** → use AWS NCAR ERA5 mirror or GEE for anything time-sensitive.
- **Vercel egress / Hobby non-commercial** → keep big tiles/COG on R2 (zero egress); use Vercel only for the Next.js shell if chosen.

---

## Sources
- IMDLIB repo: https://github.com/iamsaswata/imdlib • Docs: https://imdlib.readthedocs.io/en/latest/Usage.html • PyPI: https://pypi.org/project/imdlib/ • Paper: https://www.sciencedirect.com/science/article/abs/pii/S1364815223002554
- IMD Griddata pages: https://imdpune.gov.in/cmpg/Griddata/Rainfall_25_Bin.html • https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html • https://www.imdpune.gov.in/cmpg/Griddata/Max_1_Bin.html • https://www.imdpune.gov.in/cmpg/Griddata/Min_1_Bin.html • https://www.imdpune.gov.in/Clim_Pred_LRF_New/Grided_Data_Download.html
- IMD mirror (IRI): https://iridl.ldeo.columbia.edu/SOURCES/.IMD/.RF0p25/
- Reading IMD binary in R/NetCDF: https://ankitdeshmukh.com/post/2024-10-03-working-with-netcdf/
- MOSDAC: API manual https://www.mosdac.gov.in/downloadapi-manual • catalog https://mosdac.gov.in/catalog-app/satellite.php • INSAT-3D products https://www.mosdac.gov.in/insat-3d-data-products • 3RIMG_L2B_LST https://mosdac.gov.in/doi/190/ • format doc https://www.mosdac.gov.in/docs/INSAT3D_Products.pdf • anon-data note https://mosdac.gov.in/i-dont-have-username-and-password-mosdac-can-i-download-data
- Bhuvan API: https://bhuvan-app1.nrsc.gov.in/api/ • Geoportal: https://bhuvan.nrsc.gov.in/ngmaps • Bhoonidhi API: https://bhoonidhi.nrsc.gov.in/bhoonidhi-api/ • India-WRIS: https://indiawris.gov.in
- Google Earth Engine: catalog https://developers.google.com/earth-engine/datasets/catalog • IMERG V07 https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07 • ERA5-Land daily https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_DAILY_AGGR • ERA5 hourly https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_HOURLY
- Copernicus CDS: https://cds.climate.copernicus.eu/how-to-api • cdsapi https://github.com/ecmwf/cdsapi
- NASA earthaccess: https://www.earthdata.nasa.gov/data/tools/earthaccess • IMERG how-to https://github.com/nasa/gesdisc-tutorials
- Microsoft Planetary Computer: https://planetarycomputer.microsoft.com/docs/quickstarts/reading-stac/ • SDK https://github.com/microsoft/planetary-computer-sdk-for-python
- AWS Open Data: registry https://registry.opendata.aws/ • ERA5 (NCAR) https://registry.opendata.aws/nsf-ncar-era5/ • Sentinel-2 COGs https://registry.opendata.aws/sentinel-2-l2a-cogs/ • MODIS https://registry.opendata.aws/modis-astraea/
- Cloudflare: R2 pricing https://developers.cloudflare.com/r2/pricing/ • R2 overview https://developers.cloudflare.com/r2/ • Protomaps/PMTiles on CF https://docs.protomaps.com/deploy/cloudflare
- Vercel: limits https://vercel.com/docs/functions/limitations • pricing https://vercel.com/pricing • Hobby https://vercel.com/docs/plans/hobby
- Google Cloud Run: pricing https://cloud.google.com/run/pricing • free features https://docs.cloud.google.com/free/docs/free-cloud-features
- Hugging Face Spaces ZeroGPU: https://huggingface.co/docs/hub/en/spaces-zerogpu • Modal https://modal.com
