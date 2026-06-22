/**
 * Bharat Climate Twin — Cloudflare Worker edge stub.
 *
 * This is a DOCUMENTED STUB demonstrating the O(1) edge-serving design from
 * ARCHITECTURE.md §7 and §11. In production it replaces / fronts the Python
 * FastAPI service for the hot read path, serving everything constant-time from
 * Cloudflare's edge (330+ PoPs) with no origin compute:
 *
 *   • R2  — object store (zero egress, HTTP range reads) holding the precomputed
 *           JSON artifacts, COG/PMTiles pyramids, Zarr cube, GeoParquet.
 *   • KV  — global O(1) cache (hot read 0.5–10 ms): {h3_cell → series},
 *           {scenario_hash → delta}, hot tiles + metadata.
 *   • DO  — Durable Objects for per-session scenario state (not shown here).
 *
 * Every query is reduced to a DETERMINISTIC ADDRESS computed with arithmetic
 * (no search): point → H3 cell id → KV/array lookup; tile → PMTiles Hilbert id
 * → R2 byte range; scenario → hash(params) → KV delta. See the README for how
 * this mirrors the FastAPI endpoints so the frontend works against either.
 *
 * Bindings expected (see wrangler.toml):
 *   env.ARTIFACTS  — R2 bucket with metadata.json, fields_daily.json, ...
 *   env.KV         — KV namespace for {cell→series} / {scenario→delta} / cache
 *
 * Deploy:  npx wrangler deploy        (after `npx wrangler kv:namespace create`
 *          and uploading artifacts to R2 with `wrangler r2 object put`).
 */

const RES = 0.25; // analysis grid spacing (deg)
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

/** JSON response helper with CORS + cache headers. */
function json(body, { status = 200, cache = 0 } = {}) {
  const headers = { "Content-Type": "application/json", ...CORS };
  if (cache > 0) headers["Cache-Control"] = `public, max-age=${cache}, immutable`;
  return new Response(JSON.stringify(body), { status, headers });
}

/**
 * O(1) point → grid index, identical math to the FastAPI `data_store.py`:
 *   i = round((lat - lat0) / RES);  j = round((lon - lon0) / RES)
 * `grid` is the metadata.grid object (gives lat0/lon0 and bounds).
 */
function nearestCell(lat, lon, grid) {
  const lat0 = grid.lats[0];
  const lon0 = grid.lons[0];
  let i = Math.round((lat - lat0) / RES);
  let j = Math.round((lon - lon0) / RES);
  i = Math.max(0, Math.min(grid.nlat - 1, i));
  j = Math.max(0, Math.min(grid.nlon - 1, j));
  return [i, j];
}

/** Read + parse a JSON artifact from R2 (cached at the edge after first read). */
async function readArtifact(env, file) {
  // In production, also wrap with caches.default for a true O(1) edge hit.
  const obj = await env.ARTIFACTS.get(file);
  if (!obj) return null;
  return await obj.json();
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    // --- Health ---------------------------------------------------------- //
    if (path === "/api/health") {
      return json({ status: "ok", edge: "cloudflare-worker-stub", version: "1.0" });
    }

    // --- Verbatim artifacts (R2-backed, immutable → long cache) ---------- //
    // Mirrors api.ts: GET ${API_BASE}/<file>.json and /api/<name>.
    const ARTIFACT_MAP = {
      "/metadata.json": "metadata.json",
      "/api/metadata": "metadata.json",
      "/fields_daily.json": "fields_daily.json",
      "/api/fields_daily": "fields_daily.json",
      "/climatology.json": "climatology.json",
      "/api/climatology": "climatology.json",
      "/uncertainty.json": "uncertainty.json",
      "/api/uncertainty": "uncertainty.json",
      "/scenarios.json": "scenarios.json",
      "/api/scenarios": "scenarios.json",
      "/sources.json": "sources.json",
      "/api/sources": "sources.json",
      "/metrics.json": "metrics.json",
      "/api/metrics": "metrics.json",
    };
    if (ARTIFACT_MAP[path]) {
      const data = await readArtifact(env, ARTIFACT_MAP[path]);
      if (!data) return json({ error: "artifact not found" }, { status: 404 });
      return json(data, { cache: 86400 });
    }

    // --- O(1) point lookup ---------------------------------------------- //
    // Production: KV hot read `{h3_cell → series}` keyed by H3 id. Here we
    // demonstrate the deterministic addressing using the metadata grid.
    if (path === "/api/point") {
      const lat = parseFloat(url.searchParams.get("lat"));
      const lon = parseFloat(url.searchParams.get("lon"));
      if (Number.isNaN(lat) || Number.isNaN(lon)) {
        return json({ error: "lat and lon required" }, { status: 400 });
      }
      const meta = await readArtifact(env, "metadata.json");
      const [i, j] = nearestCell(lat, lon, meta.grid);
      // PROD: const series = await env.KV.get(`series:${cellId}`, "json");
      // (KV value pre-baked by the offline pipeline → single ~1 ms edge read.)
      const fields = await readArtifact(env, "fields_daily.json");
      const series = {};
      for (const v of ["rainfall", "tmax", "tmin"]) {
        series[v] = { values: fields[v].map((day) => day[i][j]) };
      }
      return json(
        { cell_id: `r4-${i}-${j}`, i, j, lat: meta.grid.lats[i], lon: meta.grid.lons[j], series },
        { cache: 3600 }
      );
    }

    // --- What-if: hash(params) → KV delta (O(1) lookup + trivial add) ---- //
    if (path === "/api/whatif") {
      const p = url.searchParams;
      const params = {
        temp_offset: parseFloat(p.get("temp_offset") ?? p.get("dT") ?? "0"),
        rain_pct: parseFloat(p.get("rain_pct") ?? p.get("dP") ?? "0"),
        onset_shift: parseInt(p.get("onset_shift") ?? p.get("onset") ?? "0", 10),
      };
      const key = `scenario:${params.temp_offset}_${params.rain_pct}_${params.onset_shift}`;
      // PROD: const delta = await env.KV.get(key, "json"); if hit → return O(1).
      const cached = env.KV ? await env.KV.get(key, "json") : null;
      if (cached) return json({ params, match: "library", ...cached }, { cache: 3600 });
      // Off-grid: interpolate nearest library members, or fall back to the
      // FastAPI service for a full server-side recompute (same physics).
      return json({
        params,
        match: "miss",
        note:
          "Edge KV miss → interpolate nearest library deltas, or proxy to the " +
          "FastAPI /api/whatif which recomputes with the contract physics.",
      });
    }

    // --- Map tiles: PMTiles Hilbert id → R2 byte range (1–2 GETs) -------- //
    const tileMatch = path.match(/^\/api\/tiles\/(\d+)\/(\d+)\/(\d+)\.png$/);
    if (tileMatch) {
      // PROD: resolve (z,x,y) → Hilbert TileId → {offset,length} from the
      // PMTiles directory, then a single R2 `.get(key, {range})` byte read,
      // CDN-cached. Stubbed here.
      return json(
        {
          error: "not_implemented",
          tile: { z: +tileMatch[1], x: +tileMatch[2], y: +tileMatch[3] },
          detail: "Serve via PMTiles byte-range from R2 (see ARCHITECTURE §7).",
        },
        { status: 501 }
      );
    }

    return json({ error: "not_found", path }, { status: 404 });
  },
};
