# Fast-Platform & O(1) Data-Access Techniques for the Climate Digital Twin

**Project:** ISRO BAH 2026 PS5 — "AI-Powered Digital Twin of India's Climate"
**Focus:** Achieving the *fastest possible* data access — ideally O(1) / near-constant-time lookups and serving — for high-resolution gridded climate fields (rainfall, temperature), point time series, map tiles, and "what-if" scenario recomputation, served to an interactive dashboard with a near-real-time feel.
**Date:** 2026-06-21
**Status:** Research findings + opinionated recommended architecture

---

## 0. TL;DR — The Core Insight

A digital-twin dashboard never needs to "search" for data if you **address it directly**. The fastest systems convert every query into a *deterministic address* — a byte range, a hash key, a cell ID, or a tile coordinate — that can be computed with arithmetic in O(1) and fetched in one request. Everything below is in service of that principle:

1. **Spatial → integer.** Turn (lat, lng, resolution) into a 64-bit cell ID with pure arithmetic (Uber **H3** `latLngToCell`). O(1).
2. **Tile → byte range.** Turn (z, x, y) into a byte offset with arithmetic (**PMTiles** Hilbert tile ID). O(1) addressing, 1–2 range requests.
3. **Array slice → chunk file(s).** Turn an (time, y, x) hyperslab into the exact set of chunk keys (**Zarr** / **COG** internal tiling). O(1) per chunk.
4. **Precompute the expensive stuff.** Turn model runs, scenario deltas, and aggregations into **materialized lookup tables / data cubes** so the dashboard does O(1) reads, not O(n) compute.
5. **Cache at the edge.** Put the hot addresses behind a global **KV / CDN** so the read is a sub-5 ms memory hit near the user.

"O(1)" in this document means *constant in the size of the dataset* — the cost does not grow as you add more years, more variables, or more grid points. Network round-trips still dominate wall-clock latency, so the second goal is **minimizing the number of round-trips** (ideally one) and **serving from the edge**.

---

## 1. Project data profile (what we are optimizing for)

From `idea.md`, the concrete data and access patterns are:

| Data | Native form | Resolution | Access pattern in dashboard |
|---|---|---|---|
| IMD gridded rainfall | Binary grid (→ NetCDF/GeoTIFF) | 0.25° (~28 km, ~770 km²/cell) | Map tiles + point time series + region aggregates |
| IMD max/min temperature | Binary grid | 1.0° (~111 km) | Map tiles + point time series + region aggregates |
| INSAT LST / SST / rainfall (MOSDAC) | Satellite product (HDF/GeoTIFF) | Sensor grid | Map tiles, latest-frame display |
| AI predictions / nowcasts | Model output arrays | Same grid | Map tiles + "current state" overlay |
| "What-if" scenarios | On-the-fly deltas (e.g. +2 °C, +20 % rain) | Same grid | Interactive recompute, near-instant |

**Grid sizes are small.** India at 0.25° is roughly a **130 × 130** grid (~17k cells); at 1° it is ~**32 × 32** (~1k cells). This is a *crucial* fact: an entire daily field of India fits in tens of KB, and **decades of daily data for the whole grid fit in RAM**. This makes aggressive precomputation and in-memory/edge serving completely feasible — we are not fighting petabytes, we are fighting *latency and round-trips*.

**Design implication:** favor whole-region precomputed cubes + edge KV + client-side GPU rendering over heavy server-side dynamic computation. The dataset is small enough that "precompute everything and serve O(1)" is the dominant strategy.

---

## 2. Cloud-Optimized Formats (partial / constant-time reads)

These formats let a client read *only the bytes it needs* over HTTP range requests, instead of downloading whole files. The common pattern: a small, fetched-once **index/metadata** block maps a logical request (tile, chunk, slice) to a **byte range**, then one HTTP `Range: bytes=start-end` GET retrieves it.

### 2.1 Cloud-Optimized GeoTIFF (COG) + HTTP range requests
- **What it is:** A standard GeoTIFF (now an OGC standard, [OGC 21-026](https://docs.ogc.org/is/21-026/21-026.html)) internally organized as (a) a **tiled** layout (256×256 / 512×512 internal tiles, not strips), (b) **overviews / pyramids** (pre-computed downsampled levels), and (c) a header laid out so a client can read metadata first, then `Range`-GET exactly the tiles it needs. ([cogeo.org](https://cogeo.org/), [Cloud-Native Geo Guide](https://guide.cloudnativegeo.org/cloud-optimized-geotiffs/intro.html))
- **Access complexity:** **O(1) per tile** — header read (1 request) → compute tile offset → range GET (1 request). Reading one map tile from a 50 GB COG can mean downloading "a few hundred kilobytes" instead of the whole file ([TiTiler](https://developmentseed.org/titiler/)). Overviews give O(1) zoomed-out reads (you fetch a small pyramid level, not the full grid).
- **Use here:** Store each daily/monthly rainfall & temperature field, each INSAT scene, and each AI-prediction frame as a COG. This is the canonical raster format and is consumed natively by TiTiler/rio-tiler, GDAL, QGIS, DuckDB spatial, etc.
- **Recommendation:** **Adopt COG as the on-disk raster archive format.** It is the lingua franca; everything downstream (dynamic tiling, mosaics, DuckDB) speaks it. Convert IMD binary grids → COG with `rio cogeo create` (GDAL `COG` driver), with overviews and a proper nodata/CRS.

### 2.2 Zarr / OME-Zarr + chunking + consolidated metadata
- **What it is:** A cloud-native **chunked N-dimensional array** format. The array is split into a grid of independently-stored, individually-compressed **chunk** files; one `zarr.json` (or `.zarray`/`.zattrs`) holds the schema. **Consolidated metadata** packs all chunk/array metadata into a single object so the whole hierarchy is read with **one** GET instead of many. ([Earthmover: What is Zarr](https://www.earthmover.io/blog/what-is-zarr/), [zarr consolidated metadata](https://zarr.readthedocs.io/en/latest/user-guide/consolidated_metadata/))
- **Access complexity:** **O(1) per chunk.** A `(time, lat, lon)` hyperslab maps deterministically to the exact set of chunk keys; each is one GET, and they can be fetched **in parallel**. NOAA reported Zarr giving **~40× faster time-series access** vs legacy formats ([Cloud-Native Geo Guide: Zarr](https://guide.cloudnativegeo.org/zarr/intro.html)). Chunk shape is the key tuning knob: chunk along the access axis (see §10 chunking note).
- **Use here:** Store the **analysis cube** — the full `(time, lat, lon, variable)` stack — as a single Zarr store. This is the substrate for time-series-at-a-point and for xarray/dask compute. Chunk so that a point time series (all time, single cell) is 1 chunk and a single daily map is 1 chunk (see §10).
- **Recommendation:** **Use Zarr v3 (with consolidated metadata) as the primary analytical array store**, served from object storage. Pair with **Icechunk** (transactional, versioned Zarr storage engine) if you want snapshot/rollback of model runs and reproducible scenario versions ([Icechunk](https://icechunk.io/en/latest/virtual/)).

### 2.3 Kerchunk / VirtualiZarr reference files over NetCDF/GRIB
- **What it is:** Instead of *rewriting* legacy NetCDF/GRIB/HDF into Zarr, **Kerchunk** (and the newer **VirtualiZarr**) scans the originals and emits a tiny JSON/Parquet **reference file** recording, per chunk, the source file + byte offset + length + compression. xarray then opens the collection as one **virtual Zarr** dataset, reading chunks in-place. ([Kerchunk](https://fsspec.github.io/kerchunk/), [VirtualiZarr](https://virtualizarr.readthedocs.io/), [Pangeo write-up](https://medium.com/pangeo/accessing-netcdf-and-grib-file-collections-as-cloud-native-virtual-datasets-using-kerchunk-625a2d0a9191))
- **Access complexity:** Same as Zarr (**O(1) per chunk**) *if the originals were reasonably chunked* — "Kerchunk will allow for read performance equal to newer formats like Zarr." No data duplication.
- **Use here:** IMD/MOSDAC distribute NetCDF/HDF/GRIB. Kerchunk/VirtualiZarr lets you treat the *raw archive* as a virtual cube **without a full re-encode** — great for rapid PoC and for keeping a single source of truth. Persist references with VirtualiZarr → Icechunk for fast repeat opens (far faster than `open_mfdataset`).
- **Recommendation:** **Use VirtualiZarr to virtualize the raw IMD/MOSDAC NetCDF/HDF** during ingest; materialize a *real* Zarr cube only for the hot, frequently-served subset. Best of both: no duplication for the cold archive, native Zarr speed for the hot cube.

### 2.4 GeoParquet
- **What it is:** Parquet (columnar, compressed, row-group-chunked) with a geometry column + CRS metadata; **GeoParquet 1.1** adds **spatial partitioning** (per-row-group bounding-box extents) so a reader can skip non-matching groups. ([Cloud-Native Geo Guide / Kyle Barron interview](https://cloudnativegeo.org/blog/2024/12/interview-with-kyle-barron-on-geoarrow-and-geoparquet-and-the-future-of-geospatial-data-analysis/))
- **Access complexity:** **O(row-groups), with predicate/column pushdown** → in practice near-O(matching groups). Range requests fetch only needed row groups + columns. Excellent for *tabular* outputs (station data, H3-aggregated tables, time-series-as-table).
- **Use here:** Store station/IMD-point tables, **H3-indexed aggregate tables** (cell_id, date, value), and scenario result tables. Query directly with DuckDB over HTTP.
- **Recommendation:** **Use GeoParquet (partitioned, sorted by H3 cell or time) for all tabular/vector data and precomputed aggregates.** It is the columnar twin of Zarr and the ideal DuckDB target.

### 2.5 FlatGeobuf
- **What it is:** A single-file, streamable **binary vector** format with a **packed Hilbert R-tree** spatial index in the header, so a client can `Range`-GET only the features intersecting a bounding box. ([Cloud-Native Geo Guide: FlatGeobuf index](https://guide.cloudnativegeo.org/flatgeobuf/hilbert-r-tree.html))
- **Access complexity:** **O(log n + k)** for a bbox query (R-tree descent + k results), streamed over HTTP; usable before the full file downloads.
- **Use here:** Boundaries that drive region aggregation — India states/districts/river basins. Fast bbox-filtered fetch of admin polygons for the dashboard.
- **Recommendation:** **Use FlatGeobuf for admin/basin boundary layers** (or PMTiles vector if you want pure tile serving). Secondary to GeoParquet for analytics.

### 2.6 Apache Arrow (+ Arrow Flight)
- **What it is:** A language-agnostic **columnar in-memory** format enabling **zero-copy** sharing and O(1) random column access; **Arrow Flight** is a gRPC-based wire protocol for moving Arrow batches at "wire speed." ([Arrow Flight benchmark](https://arxiv.org/pdf/2204.03032))
- **Access complexity:** **O(1) random access** within a record batch; Flight shows "**23× throughput** and **26× lower end-to-end latency** vs REST/JSON."
- **Use here:** The in-memory currency between DuckDB, pandas/Polars, the model, and the API. If a Python compute service must stream large result sets to another service, use **Arrow Flight** instead of JSON.
- **Recommendation:** **Make Arrow the in-process data currency**; use Flight only if you have a service-to-service bulk-transfer bottleneck (likely overkill for a PoC, but the right tool if it appears).

### 2.7 TileDB
- **What it is:** A multi-dimensional **array database** engine (dense + sparse), cloud-native, with native multi-language readers (C++, Java, Go, …) rather than relying on Python+Dask. ([TileDB deep dive](https://www.tiledb.com/blog/a-deep-dive-into-the-tiledb-data-format-storage-engine))
- **Access complexity:** **O(1) per tile/chunk**, like Zarr; benchmarks show **2.3–9.3× faster writes** and **up to ~7.9× faster reads vs Zarr on S3**, and it shines in the "many small chunks" regime where naive Zarr+s3fs is 2–10× slower ([TileDB benchmarks](https://github.com/TileDB-Inc/tiledb-benchmarks), [Earthmover: I/O-maxing tensors](https://www.earthmover.io/blog/i-o-maxing-tensors-in-the-cloud/)).
- **Use here:** A strong alternative to Zarr for the array cube *if* you hit Zarr/s3fs small-chunk slowness or want one engine across languages.
- **Recommendation:** **Default to Zarr** (bigger ecosystem, xarray-native, Kerchunk bridge). **Keep TileDB as the escape hatch** if S3 small-chunk read latency becomes the bottleneck. (Note: modern Rust Zarr backends — `zarrs`, `obstore`, `tensorstore` — close most of the gap, so prefer those before switching engines.)

---

## 3. Spatial Indexing for O(1) / O(log n) point & region lookups

Two families: **(a) space-filling-curve / grid systems** that map a point to an integer with arithmetic (O(1), no search), and **(b) tree indexes** (R-tree/KD/quadtree) that *search* in O(log n). For a *gridded* digital twin, the grid systems are the stars because they make "value at this point" and "aggregate over this region" into **direct lookups and integer joins**.

### 3.1 Uber H3 (hexagonal) — the recommended index ⭐
- **What it is:** A hierarchical **hexagonal** global grid (resolutions 0–15). `latLngToCell(lat, lng, res)` returns a unique **64-bit** index encoding both location and hierarchy. ([H3](https://github.com/uber/h3), [h3-py](https://uber.github.io/h3-py/intro.html), [Uber blog](https://www.uber.com/us/en/blog/h3/))
- **Access complexity:** **O(1)** — point→cell is closed-form arithmetic (project to icosahedron face → grid coordinates → index), *not* a tree search. Parent/child (`cellToParent`/`cellToChildren`), neighbors (`gridDisk`), and distance (`gridDistance`) are all O(1)/O(k) bit/coordinate ops. Joining two datasets on H3 cell ID is a hash join on a 64-bit int.
- **Why hexagons:** "Hexagons have only one class of neighbor" (squares have edge- *and* corner-neighbors), so neighbor queries, convolutions, smoothing, and uniform-distance analytics are simpler and less distorted ([H3 vs S2](https://h3geo.org/docs/comparisons/s2/)).
- **Resolution mapping for India** ([H3 res table](https://h3geo.org/docs/core-library/restable/)):

  | H3 res | Avg cell area | Avg edge | Matches |
  |---|---|---|---|
  | 2 | 86,802 km² | 182.5 km | coarse / national rollups |
  | 3 | 12,393 km² | 69.0 km | ~1° temperature grid (~111 km) region bins |
  | 4 | 1,770 km² | 26.1 km | ~0.25° rainfall grid (~770 km²) — **closest** |
  | 5 | 253 km² | 9.85 km | sub-grid / fine dashboard hover |

  → Use **res 4** as the working cell for 0.25° rainfall, **res 3** for 1° temperature, **res 2** for national summaries.
- **Use here:** (1) **Point lookup** — dashboard click (lat, lng) → `latLngToCell` → O(1) key into a precomputed `{cell_id → time-series}` table. (2) **Region aggregation** — precompute mean rainfall per H3 cell per day; region totals = group-by on cell IDs. (3) **AI feature engineering** — H3 cell as a categorical spatial feature; neighbor rings as convolution context. (4) **Choropleth tiles** — render hex aggregates client-side.
- **Recommendation:** **Adopt H3 as the universal spatial key.** Precompute an H3-indexed cube/table so *every* point/region query is an integer hash lookup. This is the single biggest "make it O(1)" lever in the project.

### 3.2 Google S2 (square cells, Hilbert curve)
- **What it is:** Projects Earth onto a cube, runs a **Hilbert curve** per face, maps to **64-bit** cell IDs; 31 levels; powers Google Maps. Containment = **prefix comparison** (very fast). ([Christian Perone](https://blog.christianperone.com/2015/08/googles-s2-geometry-on-the-sphere-cells-and-hilbert-curve/), [Ben Feifke](https://benfeifke.com/posts/geospatial-indexing-explained/))
- **Access complexity:** **O(1)** point→cell; **O(1)** ancestor/contains via Hilbert-prefix; `S2RegionCoverer` approximates arbitrary polygons with minimal cells.
- **Use here:** Viable alternative to H3, with *cleaner* hierarchy (exact aperture-4 subdivision) and excellent range-scan locality (great as a DB sort key). But square cells have two neighbor classes → messier for hex-style analytics.
- **Recommendation:** **Prefer H3** for analytics/visualization; **consider S2** only if you specifically want strict hierarchical containment or Hilbert range scans as a primary DB index.

### 3.3 Geohash (string, base-32)
- **What it is:** Recursive lat/lng bisection encoded as a base-32 **string**; shared prefix ≈ spatial proximity. ([Ben Feifke](https://benfeifke.com/posts/geospatial-indexing-explained/))
- **Access complexity:** **O(precision)** to encode (linear in #chars, i.e. constant for fixed precision); prefix queries are string range scans. Edge-case pitfalls: neighbors across prefix boundaries are non-adjacent, and equirectangular cells distort with latitude.
- **Use here:** Simple, human-readable bucketing; works as a Redis key prefix. Inferior to H3/S2 for analytics.
- **Recommendation:** **Skip in favor of H3** unless you need plain string prefixes for trivial bucketing.

### 3.4 Morton / Z-order & Hilbert space-filling curves
- **What it is:** Map N-D integer coordinates → 1-D key by bit-interleaving (Morton/Z) or Hilbert traversal, preserving locality so multi-dim range queries become 1-D range scans. Hilbert preserves locality better; Morton is cheaper to compute. ([SFC study](https://arxiv.org/pdf/1606.06133))
- **Access complexity:** **O(1)** encode/decode (bit ops); enables 1-D range scans for 2-D/3-D windows.
- **Use here:** Order COG internal tiles, Zarr chunks, GeoParquet rows, and PMTiles tiles so spatially-near data is byte-near (fewer, more contiguous range requests). It's the *plumbing* under PMTiles (Hilbert tile IDs), FlatGeobuf (Hilbert R-tree), and S2 (Hilbert curve).
- **Recommendation:** **Sort/lay out storage in Hilbert order** (GeoParquet, tile archives). Mostly automatic via PMTiles/FlatGeobuf; for custom GeoParquet, sort rows by H3 cell or Hilbert key before writing.

### 3.5 R-tree / KD-tree / quadtree / octree
- **What it is:** Hierarchical **search** trees. R-tree (overlapping bbox nodes, balanced) is the standard for *polygons/lines*; KD-tree for point NN; quadtree/octree for adaptive 2-D/3-D subdivision. ([DZone quadtree/Hilbert](https://dzone.com/articles/algorithm-week-spatial))
- **Access complexity:** **O(log n)** typical lookup (worst case worse with overlap). "R-trees are the only known algorithm for effectively indexing **shapes**; space-filling-curve methods are only well-suited to indexing **points**" ([search synthesis](https://dzone.com/articles/algorithm-week-spatial)).
- **Use here:** Behind the scenes — FlatGeobuf's packed Hilbert R-tree for boundary bbox queries; DuckDB spatial / PostGIS R-tree (GiST) for polygon intersection (point-in-state, basin membership).
- **Recommendation:** **Lean on built-in R-trees** (FlatGeobuf header, DuckDB/PostGIS) for the *polygon* operations H3 can't do exactly; use **H3** for the point/grid operations where O(1) wins.

---

## 4. Tiling & Pyramids for Maps

Map UX speed is dominated by **tile addressing**: turning `(z, x, y)` into bytes with minimal round-trips.

### 4.1 XYZ / TMS raster tiles + overviews/pyramids
- **What it is:** The web-map standard: the world is a quadtree of 256×256 tiles addressed by `z/x/y`. **Pyramids/overviews** store each zoom pre-downsampled so a zoomed-out view fetches few small tiles. ([cogeo overviews](https://guide.cloudnativegeo.org/cloud-optimized-geotiffs/intro.html))
- **Access complexity:** **O(1)** addressing — `(z,x,y)` is a direct path/byte-range; one GET per visible tile (a viewport is a bounded constant number).
- **Use here:** The fundamental delivery unit for every raster layer (rainfall, temp, INSAT, predictions).
- **Recommendation:** Standard XYZ tiling for all map layers, with overviews down to z0.

### 4.2 Vector tiles (MVT)
- **What it is:** Mapbox Vector Tile — `(z,x,y)`-addressed protobuf of *vector* geometry, styled and rendered client-side.
- **Access complexity:** **O(1)** addressing; tiny payloads; infinite client-side restyling without re-fetch.
- **Use here:** Boundaries, H3 hex choropleths, station points, labels.
- **Recommendation:** Use MVT (packaged in PMTiles) for all vector overlays.

### 4.3 PMTiles (single-file tile archive with range reads) ⭐
- **What it is:** A **single file** holding an entire tile pyramid (raster *or* vector). v3 maps `(z,x,y)` → one **64-bit Hilbert TileId** → a directory entry `{offset, length}`; the client `Range`-GETs just that tile. **Run-length encoding** collapses repeated tiles (e.g., one ocean tile reused 107,977× → a single 24-byte entry, ~75,000:1). The v3 initial request is just **16 KB** (down from 512 KB in v2). ([PMTiles v3 Hilbert IDs](https://protomaps.com/blog/pmtiles-v3-hilbert-tile-ids/), [PMTiles docs](https://docs.protomaps.com/pmtiles/), [Cloud-Native Geo Guide: PMTiles](https://guide.cloudnativegeo.org/pmtiles/intro.html))
- **Access complexity:** **O(1) tile addressing**; typically **1–2 range requests** per tile (root directory cached after first read; one leaf-dir read for deep pyramids; one tile read). **No tile server, no database — just a static file on object storage + a CDN.** A real-world case packed **116 GB of satellite data → ~60M tiles** into PMTiles ([geotiff2pmtiles](https://www.pascalspoerri.ch/blog/2026-02-15-geotiff2pmtiles/)).
- **Use here:** **The serving format for all pre-rendered map layers.** Build one PMTiles per layer per timestep (or a time-multiplexed archive), drop on R2/S3, serve via CDN, render with MapLibre + the PMTiles protocol plugin. Zero serverless cost, global edge caching, O(1) reads.
- **Recommendation:** **Make PMTiles the default tile-delivery mechanism.** It is the single best fit for "fastest, cheapest, O(1), serverless" map serving and aligns perfectly with the edge/CDN strategy in §6.

### 4.4 TiTiler / dynamic tiling, rio-tiler, MosaicJSON
- **What it is:** **TiTiler** (FastAPI + rio-tiler/GDAL) generates `(z,x,y)` tiles **on the fly** directly from COGs, reading only needed bytes. **MosaicJSON** describes how many COGs mosaic into one virtual layer; **rio-tiler** is the underlying read engine. ([TiTiler](https://github.com/developmentseed/titiler), [rio-tiler](https://cogeotiff.github.io/rio-tiler/), [MosaicJSON overview](https://kylebarron.dev/blog/cog-mosaic/overview/))
- **Access complexity:** Per tile, **O(1)** byte reads from the COG, but with **on-demand server compute** (rescale/colormap) — slower than a pre-baked PMTiles tile, faster to *update*. "Instead of downloading a 50 GB GeoTIFF … may only need a few hundred kilobytes." Runs serverless on AWS Lambda.
- **Use here:** **Dynamic/interactive layers**: user-chosen colormap/rescale, arbitrary date selection, **what-if scenario tiles** (apply +2 °C then tile), band math — anything where pre-baking every combination is impractical. Put a CDN in front so repeated tiles become O(1) cache hits.
- **Recommendation:** **Use TiTiler for the dynamic/scenario layers; PMTiles for the stable/precomputed layers.** Hybrid: bake the common cases to PMTiles, fall back to TiTiler for the long tail, CDN-cache both.

---

## 5. Fast Stores / Engines

### 5.1 Redis (hash O(1) GET)
- **What it is:** In-memory key-value store; hash-table `GET`/`HGET` is **O(1)**; sub-millisecond on a warm instance. ("As a hash table grows it is resized to maintain O(1) access" — [Redis internals](https://machine-learning-made-simple.medium.com/why-redis-is-so-fast-part-1-the-historical-foundations-b316d85ee58c).)
- **Use here:** Hot cache for `{H3 cell → latest value}`, `{cell → time series}`, `{scenario hash → result}`, recent-tile bytes, API responses. Given the *small* India grid, **the entire current state can live in Redis**.
- **Recommendation:** **Use Redis as the server-side hot-path cache** for point lookups and scenario results. (At the edge, Cloudflare KV plays the same role globally — §6.)

### 5.2 DuckDB (+ spatial + httpfs over Parquet/COG)
- **What it is:** In-process OLAP engine. With **httpfs** it reads Parquet/COG over HTTP using **range requests + Parquet metadata** to fetch only needed row-groups/columns; **spatial** adds geometry types + R-tree. ([DuckDB httpfs](https://duckdb.org/docs/current/core_extensions/httpfs/https), [read-through cache](https://medium.com/@hadiyolworld007/duckdb-read-through-caches-on-http-range-requests-lakehouse-speed-on-plain-object-storage-d43a499f7b50))
- **Access complexity:** Predicate/column **pushdown** → near-O(matching row-groups). ⚠️ **Caveat:** naive remote Parquet reads can fan out into *huge* request counts (one issue cites **150K requests** for a wide file ([duckdb-httpfs #172](https://github.com/duckdb/duckdb-httpfs/issues/172))) — mitigate with the HTTP metadata cache, sensible row-group sizes, and partitioning. DuckDB-Wasm currently **lacks the spatial extension**.
- **Use here:** The **analytics brain**: ad-hoc aggregations, H3 group-bys, joining station/Parquet tables, time-series rollups — directly over GeoParquet/COG on object storage, no warehouse to run.
- **Recommendation:** **Use DuckDB (server-side) as the query engine over GeoParquet**, pre-sorted/partitioned by H3 and time. Precompute hot aggregates into materialized Parquet (§7) so the dashboard hits O(1) lookups, not live scans.

### 5.3 ClickHouse
- **What it is:** Columnar OLAP DB (C++), built for billion-row aggregations.
- **Access complexity:** Sub-second large aggregations; **6–7× faster than TimescaleDB**, e.g. ~204 ms avg vs InfluxDB 428 ms vs Timescale 572 ms; **2–4M inserts/s**, 15–30× compression. ([ClickHouse vs TSDBs 2025/2026](https://sanj.dev/post/clickhouse-timescaledb-influxdb-time-series-comparison/), [KX TSBS](https://kx.com/blog/benchmarking-kdb-x-vs-questdb-clickhouse-timescaledb-and-influxdb-with-tsbs/))
- **Use here:** Only if the time-series/station volume grows large (many years × many stations × sub-daily). Overkill for the PoC's small grid.
- **Recommendation:** **Defer.** Start with DuckDB + Parquet; **graduate to ClickHouse** only if concurrent heavy aggregation at national scale demands a persistent server.

### 5.4 Apache Arrow Flight
- See §2.6 — **23× throughput / 26× lower latency vs REST/JSON**. Use for bulk service-to-service transfer if needed; likely unnecessary for the PoC.

### 5.5 Time-series DBs (TimescaleDB, InfluxDB)
- **What it is:** Timescale = Postgres + hypertables + continuous aggregates (auto-maintained materialized rollups); InfluxDB 3 = Rust/Arrow/Parquet engine.
- **Access complexity:** **Continuous aggregates** turn rollup queries into O(1) reads of precomputed buckets — conceptually the same precompute win, in a DB.
- **Use here:** If you want station/point time series in a managed SQL DB with hypertables + continuous aggregates, Timescale is a clean fit and gives you PostGIS too.
- **Recommendation:** **Optional.** DuckDB+Parquet+materialized rollups covers the PoC; choose **TimescaleDB** if you want a single Postgres/PostGIS server with built-in continuous aggregates for live station ingest.

### 5.6 Key-value patterns, materialized views & perfect hashing
- **Materialized views / precomputed summaries** "store query results physically instead of recomputing," eliminating on-demand joins/aggregations and "speeding up dashboards while reducing load" ([Databricks](https://www.databricks.com/blog/what-are-materialized-views)). This is the core O(1) trick — see §7.
- **Perfect hashing:** for a *fixed, known* key set (e.g., all India H3 res-4 cell IDs ≈ a few thousand), a **minimal perfect hash** gives **collision-free O(1)** array-index lookups with no wasted space — ideal for a fixed cell→array-slot map in a tight inner loop or on the edge.
- **Recommendation:** **Precompute aggressively; serve via KV/array indexed by H3.** For the fixed India cell set, a perfect-hash (or just a dense int array indexed by a compact cell enumeration) makes lookups branch-free O(1).

---

## 6. Edge / Serverless / CDN

The dashboard "near-real-time feel" is won or lost on **network latency**. Serve precomputed bytes from a PoP near the user.

### 6.1 Cloudflare Workers + R2 + KV + Durable Objects ⭐
- **Workers KV:** global eventually-consistent KV. **Hot reads 500 µs–10 ms** (internal p99 **< 5 ms**; the prior third-party store was ~80 ms p50 / 200 ms p99), serving **millions of GET/s** over **hundreds of billions** of keys; **values up to 25 MiB**; median object 288 B; writes propagate globally in **up to ~60 s**. ([KV docs](https://developers.cloudflare.com/kv/), [How KV works](https://developers.cloudflare.com/kv/concepts/how-kv-works/), [KV rearchitecture](https://blog.cloudflare.com/rearchitecting-workers-kv-for-redundancy/))
- **R2:** S3-compatible object storage with **no egress fees** and native HTTP **range requests** — perfect for COG/PMTiles/Zarr.
- **Durable Objects:** single-instance, strongly-consistent stateful objects routed to one PoP — for coordination/per-session scenario state.
- **Workers:** V8-isolate compute at **330+ PoPs**, sub-ms cold starts, **sub-50 ms p50** to users. ([Cloudflare 2024 stack](https://jacar.es/en/cloudflare-workers-edge-2024/))
- **Access complexity:** KV hot read = **O(1) edge memory hit**; R2 range read = **O(1)** byte fetch; both cached at the PoP.
- **Use here:** **R2** holds COG/PMTiles/Zarr (zero egress). **KV** holds `{H3 cell → latest value}`, `{scenario hash → precomputed result}`, hot tiles/metadata. **Workers** do PMTiles range-read proxying, scenario-key lookups, and tiny on-edge math (apply a precomputed delta). **Durable Objects** hold live per-session scenario state.
- **Recommendation:** **Build the serving tier on Cloudflare: R2 (storage) + KV (O(1) global lookups) + Workers (edge logic) + CDN (tile caching).** This is the strongest "fastest platform" answer for global, low-latency, near-O(1) serving with minimal ops/cost.

### 6.2 Vercel Edge
- Edge Functions/Middleware at the CDN edge; great for a Next.js dashboard front-end and light edge logic. **Recommendation:** Use Vercel (or Cloudflare Pages) for the **front-end**; keep the heavy O(1) data plane on Cloudflare R2/KV.

### 6.3 CDN caching of tiles + range-request caching + precomputed pyramids
- **What it is:** CDNs cache `(z,x,y)` tiles and honor/cache **range requests**, so PMTiles/COG sub-reads and TiTiler outputs become edge hits after first fetch.
- **Access complexity:** Cache hit = **O(1)** edge read. Precomputing full pyramids on object storage means *every* tile is a static cache-friendly object.
- **Recommendation:** **Precompute pyramids to PMTiles on R2; front everything with the CDN; set long cache-control on immutable tiles** (version the URL per data update). Turn dynamic TiTiler tiles into cache hits via stable URLs.

---

## 7. Precomputation — turning expensive queries into O(1) lookups (the master strategy)

Because the India grid is **small**, precompute the hot paths and serve O(1):

| Expensive at query time | Precompute to | Lookup cost |
|---|---|---|
| Point time series (read all dates for a cell) | `{H3 cell → series}` in KV/Redis or Zarr chunked along time | **O(1)** key/chunk |
| Region aggregate (mean over a state) | Per-cell daily means + admin→cell membership table; or materialized `{region,date → stat}` | **O(1)** lookup |
| Map for a date/variable | Pre-baked **PMTiles** pyramid per date/variable | **O(1)** tile |
| "What-if" (+2 °C, +20 % rain) | **Precomputed scenario deltas** keyed by `hash(scenario params)`; apply to baseline | **O(1)** lookup (+ trivial add) |
| Climatology / anomalies / trends | **Summary data cube** (means, percentiles, anomalies) | **O(1)** slice |

- **Materialized tiles & lookup tables:** bake the common date/variable/colormap combos to PMTiles + KV.
- **Precomputed scenario deltas:** for *linear* what-ifs (uniform shift/scale), store baseline + apply the delta on the edge in O(1); for *nonlinear* AI scenarios, precompute a discrete grid of parameter values and **interpolate** between nearest precomputed runs (O(1) lookup + lerp), reserving full model inference (§8) for novel parameters only.
- **Summary cubes / data cubes (Open Data Cube, xarray datacubes):** ODC/xarray organize Analysis-Ready Data into queryable `(time, lat, lon, var)` cubes ([Earth System Data Cubes](https://arxiv.org/html/2408.02348v1), [xcube](https://xcube.readthedocs.io/en/latest/dataaccess.html)). Materialize derived cubes (monthly means, percentiles, anomaly indices) so analytics read precomputed slices.
- **Recommendation:** **Precompute three artifacts on every data/model update:** (1) the **Zarr analysis cube** (chunked for both map-slice and point-series access), (2) **PMTiles pyramids** for all standard layers, (3) an **H3-indexed KV/Parquet table** of latest values + summary stats + scenario deltas. The dashboard then does **only O(1) reads**.

---

## 8. Compute Acceleration

For the parts that *must* compute (ingest, model inference, novel scenarios, on-the-fly tiles):

- **Vectorized NumPy:** baseline — replace Python loops with array ops (often 10–100× faster); the India grid fits in cache.
- **xarray + Dask:** labeled N-D arrays over Zarr with **lazy, chunk-parallel** compute; scales the cube to many cores/nodes without code changes.
- **GPU — CuPy / RAPIDS / cuSpatial:** CuPy is a drop-in NumPy on GPU ("**>100×**" on some ops); **cupy-xarray** runs GPU-backed xarray; **cuSpatial** accelerates spatial joins/point-in-polygon; RAPIDS targets **5–10×** over CPU. ([CuPy](https://cupy.dev/), [cuSpatial](https://github.com/rapidsai/cuspatial), [RAPIDS](https://rapids.ai/)). Use for AI inference and heavy batch recompute.
- **WebGL / WebGPU client-side rendering:** **deck.gl** (WebGL2, **WebGPU** on the roadmap/experimental — "~2× fps on Apple Silicon") + **MapLibre GL** render rasters/hex layers on the user's GPU; deck.gl has handled **30 GB** client-side ([deck.gl what's new](https://deck.gl/docs/whats-new), [MapLibre](https://maplibre.org/projects/gl-js/)). Offloads rendering from the server entirely.
- **GPU model inference:** TensorFlow/PyTorch on GPU for the nowcast/prediction model; export to ONNX/TF-Lite for fast serving; cache outputs (they become the precomputed cube of §7).
- **Recommendation:** **NumPy/xarray+Dask over Zarr for ingest & batch; GPU (CuPy/PyTorch) for model inference and novel-scenario recompute; deck.gl+MapLibre (WebGPU when stable) for client-side rendering** so the server ships *data*, not pixels.

---

## 9. Comparison Table (technique | complexity | best-for | tradeoffs)

| Technique | Access complexity | Best-for in this project | Tradeoffs |
|---|---|---|---|
| **COG + range reads** | O(1)/tile (1 hdr + 1 range GET) | Raster archive; source for tiling/DuckDB | Need correct internal tiling+overviews; raster only |
| **Zarr v3 + consolidated meta** | O(1)/chunk, parallel | Analysis cube; point time series | Chunk shape critical; small-chunk S3 latency |
| **Kerchunk / VirtualiZarr** | O(1)/chunk (≈Zarr) | Virtualize raw IMD/MOSDAC NetCDF/HDF, no copy | Depends on source chunking; ref-file upkeep |
| **GeoParquet (1.1)** | ~O(matching row-groups) | Tabular/vector + H3 aggregates for DuckDB | Group-level (not row) skipping; tune row-groups |
| **FlatGeobuf** | O(log n + k) bbox | Admin/basin boundary fetch | Vector only; row-oriented |
| **Apache Arrow / Flight** | O(1) in-memory; 23–26× vs JSON | In-proc currency; bulk transfer | Flight infra overhead for small data |
| **TileDB** | O(1)/tile; 2–9× vs Zarr/S3 | Array cube if Zarr+S3 too slow | Smaller ecosystem; another engine |
| **H3 (hex)** ⭐ | **O(1)** point→cell; O(k) neighbors | Universal spatial key; point lookup; aggregation; AI features | Cells don't perfectly nest (approx hierarchy) |
| **S2 (square)** | O(1) point→cell; O(1) contains | Strict hierarchy; Hilbert range scans | 2 neighbor classes; less hex-friendly analytics |
| **Geohash** | O(precision) encode | Trivial string bucketing | Boundary/lat distortion; weak for analytics |
| **Morton/Hilbert SFC** | O(1) encode/decode | Storage layout / range locality | Points only; Morton has long jumps |
| **R-tree / KD / quadtree** | O(log n) | Polygon ops (point-in-region) | Slower than O(1) grids; overlap (R-tree) |
| **XYZ/TMS + overviews** | O(1) addressing | All map layers | Many small files unless archived |
| **Vector tiles (MVT)** | O(1) addressing | Boundaries, hex choropleths, labels | Needs client styling |
| **PMTiles** ⭐ | O(1) addr; 1–2 range GETs | Serverless tile delivery (raster+vector) | Rebuild archive to update; range-read client |
| **TiTiler / rio-tiler / MosaicJSON** | O(1) bytes + server compute | Dynamic colormap/date/scenario tiles | Needs running service; CDN-cache to keep fast |
| **Redis** | O(1) GET, sub-ms | Server hot cache (cell→value, scenarios) | In-memory cost; single-region |
| **DuckDB + httpfs + spatial** | ~O(matching groups), pushdown | Analytics over Parquet/COG | Request fan-out; Wasm lacks spatial |
| **ClickHouse** | sub-s aggregations; 6–7× Timescale | National-scale TS/aggregation (later) | Server to run; overkill for PoC |
| **TimescaleDB / InfluxDB** | O(1) via continuous aggregates | Managed station TS + rollups | Slower aggregations than ClickHouse |
| **Cloudflare KV** ⭐ | **O(1)** hot read 0.5–10 ms | Global O(1) lookups (cell/scenario/tile) | Eventual consistency (~60 s) |
| **Cloudflare R2** | O(1) range read; no egress | COG/PMTiles/Zarr storage | Cloudflare-specific |
| **Durable Objects** | O(1) routed, strong-consistent | Per-session scenario state | Single-instance throughput |
| **CDN tile/range cache** | O(1) on hit | Cache PMTiles/COG/TiTiler tiles | Invalidation; version URLs |
| **NumPy / xarray+Dask** | O(n) compute, vectorized/parallel | Ingest & batch cube compute | CPU-bound at large n |
| **CuPy / RAPIDS / cuSpatial** | O(n) on GPU, 5–100× | AI inference; novel-scenario recompute | GPU dependency |
| **deck.gl / MapLibre (WebGPU)** | client GPU render | Offload rendering to client | Client GPU/browser variance |
| **Materialized views / data cubes / perfect hash** | **O(1)** lookup | Turn heavy queries → precomputed reads | Storage + refresh; staleness |

---

## 10. A note on chunking (the make-or-break tuning knob)

Zarr/COG/TileDB speed lives and dies by **chunk shape vs access pattern** ([chunk-size study](https://d197for5662m48.cloudfront.net/documents/publicationstatus/129928/preprint_pdf/aa1ef041a20d28b38262dc6bca5ed109.pdf)). The dashboard has **two** access patterns, in tension:

- **Map view** = one date, all (lat, lon) → chunk so a **full spatial slice for one timestep** is ~one chunk: `(time=1, lat=all, lon=all)`.
- **Point time series** = one (lat, lon), all dates → chunk so a **full time series for a cell** is ~one chunk: `(time=all, lat=small, lon=small)`.

You can't optimize both in one layout. **Solution: store two representations** (cheap, because the grid is tiny): a **time-chunked** cube for series + a **space-chunked** cube (or just the PMTiles pyramids) for maps. This dual-cube trick is the practical key to O(1)-feeling reads for *both* dashboard modes.

---

## 11. RECOMMENDED FAST-PLATFORM ARCHITECTURE ⭐

An opinionated stack maximizing speed for this digital twin. Design rule: **every interactive read is O(1) and served from the edge; all O(n) work happens offline in a precompute pipeline.**

```
                         ┌──────────────────────────────────────────────┐
   RAW (cold archive)    │  IMD binary grids · MOSDAC INSAT HDF/NetCDF    │
                         └───────────────┬──────────────────────────────┘
                                         │  VirtualiZarr / Kerchunk (no copy)
                                         ▼
                         ┌──────────────────────────────────────────────┐
   INGEST / PRECOMPUTE   │  xarray + Dask  (CPU)   ·   PyTorch/CuPy (GPU) │
   (offline, O(n) once)  │  - build Zarr analysis cube (DUAL chunking)    │
                         │  - run AI nowcast → predicted fields           │
                         │  - aggregate to H3 (res 4 rain / res 3 temp)   │
                         │  - precompute scenario deltas + summary cube   │
                         │  - bake PMTiles pyramids (raster + hex MVT)    │
                         └───────────────┬──────────────────────────────┘
                                         │  publish artifacts (versioned)
                                         ▼
                         ┌──────────────────────────────────────────────┐
   STORAGE (Cloudflare)  │  R2 (no egress, range reads):                  │
                         │   • COG archive  • Zarr cubes  • PMTiles       │
                         │   • GeoParquet (H3-/time-sorted aggregates)    │
                         │  KV (O(1) global, 0.5–10 ms hot):              │
                         │   • {H3 cell → latest value / series ptr}      │
                         │   • {hash(scenario) → precomputed result}      │
                         │   • hot tile + metadata cache                  │
                         │  Durable Objects: per-session scenario state   │
                         └───────────────┬──────────────────────────────┘
                                         │
              ┌──────────────────────────┼───────────────────────────────┐
              ▼ (O(1) static)            ▼ (O(1) lookup)                   ▼ (dynamic, long-tail)
   ┌────────────────────┐   ┌────────────────────────────┐   ┌──────────────────────────┐
   │ CDN + Workers       │   │ Workers (edge logic)        │   │ TiTiler (serverless)      │
   │ serve PMTiles tiles │   │ - cell→value KV lookups     │   │ - dynamic colormap/date   │
   │ via range reads     │   │ - apply precomputed delta   │   │ - novel what-if tiles     │
   │ (1–2 GETs, cached)  │   │   in O(1) for what-ifs      │   │ from COG; CDN-cached       │
   └─────────┬──────────┘   └──────────────┬─────────────┘   └─────────────┬────────────┘
             │                              │                               │
             └──────────────────────────────┼──────────────────────────────┘
                                            ▼
                         ┌──────────────────────────────────────────────┐
   CLIENT (browser)      │  MapLibre GL + deck.gl (WebGL2 → WebGPU)       │
                         │  - PMTiles protocol (range reads to R2/CDN)    │
                         │  - GPU client-side raster/hex rendering        │
                         │  - (optional) DuckDB-Wasm over GeoParquet      │
                         └──────────────────────────────────────────────┘
```

### The concrete blueprint ("data-cube + H3 + COG/PMTiles + Cloudflare/edge KV")

| Layer | Choice | Why it's O(1) / near-constant-time |
|---|---|---|
| **Raw/cold** | NetCDF/HDF virtualized by **VirtualiZarr/Kerchunk** | No re-encode; chunks read in-place, O(1)/chunk |
| **Analysis cube** | **Zarr v3**, consolidated metadata, **dual chunking** (time-chunked + space-chunked) | Hyperslab → exact chunk keys, parallel O(1)/chunk |
| **Raster archive** | **COG** (overviews) on R2 | Header + range GET = O(1)/tile |
| **Spatial key** | **Uber H3** (res 4 rain, res 3 temp, res 2 national) | `latLngToCell` = O(1); joins/aggregations = int hash |
| **Tabular/aggregates** | **GeoParquet** sorted by H3/time, queried by **DuckDB** | Row-group pushdown ≈ O(matching groups) |
| **Map tiles (stable)** | **PMTiles** (raster + hex MVT) on R2 + **CDN** | `(z,x,y)`→Hilbert ID→byte range; 1–2 cached GETs |
| **Map tiles (dynamic)** | **TiTiler** serverless over COG, CDN-cached | O(1) bytes + edge cache hit on repeat |
| **Point/scenario lookups** | **Cloudflare KV** (`cell→value`, `scenario→result`); Redis server-side | Hot read 0.5–10 ms, O(1) edge memory hit |
| **What-if** | **Precomputed deltas** + O(1) edge add; interpolate precomputed runs; GPU only for novel cases | Lookup + trivial arithmetic = O(1) |
| **Session state** | **Durable Objects** | Strong-consistent, routed to one PoP |
| **Compute** | xarray+Dask (CPU) ingest; **CuPy/PyTorch GPU** inference | Offline O(n); results cached → O(1) reads |
| **Client render** | **MapLibre GL + deck.gl** (WebGPU when stable) | GPU renders on client; server ships data, not pixels |
| **Front-end host** | Vercel / Cloudflare Pages (edge) | Sub-50 ms p50 from 330+ PoPs |

### Why this is the *fastest* answer
- **No search anywhere on the hot path.** Point → H3 cell ID (O(1)) → KV/array lookup (O(1)). Tile → Hilbert ID → byte range (O(1)). Slice → chunk keys (O(1)). Scenario → hash key → precomputed delta (O(1)).
- **One round-trip, served at the edge.** R2 range reads + KV hot reads + CDN tile cache mean the typical interaction is a single sub-10 ms fetch from a nearby PoP — no origin DB, often no server compute.
- **Precompute kills the O(n) work.** The small India grid lets us bake cubes, pyramids, aggregates, and scenario deltas ahead of time; the dashboard only *reads*.
- **GPU on both ends.** GPU for model inference/recompute (CuPy/PyTorch), GPU for rendering (deck.gl/WebGPU) — the CPU/server is never the bottleneck.
- **Serverless & cheap.** PMTiles + R2 (no egress) + KV + Workers = global, autoscaling, near-zero idle cost — ideal for a PoC that must also present a "scalable national framework."

### Pragmatic PoC build order
1. **Ingest:** IMD/MOSDAC → VirtualiZarr → **Zarr cube** (dual-chunked) + **COG** archive.
2. **Index:** aggregate to **H3** tables → **GeoParquet**; load latest values into **KV/Redis**.
3. **Tiles:** bake **PMTiles** for rainfall/temp/predictions → **R2 + CDN**; stand up **TiTiler** for dynamic layers.
4. **Edge:** **Workers** for `cell→value` and `scenario→delta` O(1) lookups; **Durable Objects** for sessions.
5. **Client:** **MapLibre + deck.gl** dashboard reading PMTiles + KV; what-if via precomputed deltas, GPU model only for novel parameters.
6. **Scale-out (later):** add **ClickHouse/TimescaleDB** if national TS volume grows; **TileDB** if Zarr+S3 small-chunk latency bites.

---

## Sources

**Cloud-optimized formats**
- COG: [cogeo.org](https://cogeo.org/) · [in-depth](https://cogeo.org/in-depth.html) · [OGC 21-026 standard](https://docs.ogc.org/is/21-026/21-026.html) · [Cloud-Native Geo Guide](https://guide.cloudnativegeo.org/cloud-optimized-geotiffs/intro.html)
- Zarr: [Earthmover — What is Zarr](https://www.earthmover.io/blog/what-is-zarr/) · [Consolidated metadata](https://zarr.readthedocs.io/en/latest/user-guide/consolidated_metadata/) · [Cloud-Native Geo Guide: Zarr](https://guide.cloudnativegeo.org/zarr/intro.html) · [Chunk-size study (PDF)](https://d197for5662m48.cloudfront.net/documents/publicationstatus/129928/preprint_pdf/aa1ef041a20d28b38262dc6bca5ed109.pdf)
- Kerchunk/VirtualiZarr: [kerchunk docs](https://fsspec.github.io/kerchunk/) · [VirtualiZarr](https://virtualizarr.readthedocs.io/) · [Pangeo write-up](https://medium.com/pangeo/accessing-netcdf-and-grib-file-collections-as-cloud-native-virtual-datasets-using-kerchunk-625a2d0a9191) · [Icechunk virtual](https://icechunk.io/en/latest/virtual/)
- GeoParquet/FlatGeobuf/Arrow/TileDB: [Kyle Barron interview (GeoParquet/GeoArrow)](https://cloudnativegeo.org/blog/2024/12/interview-with-kyle-barron-on-geoarrow-and-geoparquet-and-the-future-of-geospatial-data-analysis/) · [FlatGeobuf Hilbert R-tree](https://guide.cloudnativegeo.org/flatgeobuf/hilbert-r-tree.html) · [Arrow Flight benchmark (PDF)](https://arxiv.org/pdf/2204.03032) · [TileDB deep dive](https://www.tiledb.com/blog/a-deep-dive-into-the-tiledb-data-format-storage-engine) · [TileDB vs Zarr benchmarks](https://github.com/TileDB-Inc/tiledb-benchmarks) · [Earthmover — I/O-maxing tensors](https://www.earthmover.io/blog/i-o-maxing-tensors-in-the-cloud/)

**Spatial indexing**
- H3: [uber/h3](https://github.com/uber/h3) · [h3-py](https://uber.github.io/h3-py/intro.html) · [Uber blog](https://www.uber.com/us/en/blog/h3/) · [H3 vs S2](https://h3geo.org/docs/comparisons/s2/) · [resolution table](https://h3geo.org/docs/core-library/restable/)
- S2/Geohash/SFC/trees: [Ben Feifke — Geohash/S2/H3](https://benfeifke.com/posts/geospatial-indexing-explained/) · [Christian Perone — S2](https://blog.christianperone.com/2015/08/googles-s2-geometry-on-the-sphere-cells-and-hilbert-curve/) · [SFC energy/locality (PDF)](https://arxiv.org/pdf/1606.06133) · [Quadtrees & Hilbert curves](https://dzone.com/articles/algorithm-week-spatial)

**Tiling & pyramids**
- PMTiles: [v3 Hilbert tile IDs](https://protomaps.com/blog/pmtiles-v3-hilbert-tile-ids/) · [docs](https://docs.protomaps.com/pmtiles/) · [Cloud-Native Geo Guide](https://guide.cloudnativegeo.org/pmtiles/intro.html) · [116 GB → 60M tiles](https://www.pascalspoerri.ch/blog/2026-02-15-geotiff2pmtiles/)
- TiTiler/rio-tiler/Mosaic: [titiler](https://github.com/developmentseed/titiler) · [TiTiler site](https://developmentseed.org/titiler/) · [rio-tiler](https://cogeotiff.github.io/rio-tiler/) · [MosaicJSON overview](https://kylebarron.dev/blog/cog-mosaic/overview/)

**Stores/engines**
- DuckDB: [httpfs HTTP(S)](https://duckdb.org/docs/current/core_extensions/httpfs/https) · [read-through cache on range requests](https://medium.com/@hadiyolworld007/duckdb-read-through-caches-on-http-range-requests-lakehouse-speed-on-plain-object-storage-d43a499f7b50) · [request fan-out issue](https://github.com/duckdb/duckdb-httpfs/issues/172)
- ClickHouse/TSDB: [ClickHouse vs Timescale vs InfluxDB 2026](https://sanj.dev/post/clickhouse-timescaledb-influxdb-time-series-comparison/) · [KX TSBS benchmark](https://kx.com/blog/benchmarking-kdb-x-vs-questdb-clickhouse-timescaledb-and-influxdb-with-tsbs/)
- Redis / materialized views / perfect hashing: [Why Redis is fast](https://machine-learning-made-simple.medium.com/why-redis-is-so-fast-part-1-the-historical-foundations-b316d85ee58c) · [Databricks — materialized views](https://www.databricks.com/blog/what-are-materialized-views)

**Edge/serverless/CDN**
- Cloudflare: [KV docs](https://developers.cloudflare.com/kv/) · [How KV works](https://developers.cloudflare.com/kv/concepts/how-kv-works/) · [KV rearchitecture (latency)](https://blog.cloudflare.com/rearchitecting-workers-kv-for-redundancy/) · [Durable Objects](https://www.cloudflare.com/products/durable-objects/) · [2024 edge stack](https://jacar.es/en/cloudflare-workers-edge-2024/)

**Compute acceleration**
- [CuPy](https://cupy.dev/) · [RAPIDS cuSpatial](https://github.com/rapidsai/cuspatial) · [RAPIDS](https://rapids.ai/) · [deck.gl what's new](https://deck.gl/docs/whats-new) · [MapLibre GL JS](https://maplibre.org/projects/gl-js/)

**Data cubes / precomputation**
- [Earth System Data Cubes (arXiv)](https://arxiv.org/html/2408.02348v1) · [xcube data access](https://xcube.readthedocs.io/en/latest/dataaccess.html)
