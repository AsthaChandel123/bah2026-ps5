// Basemap styles for MapLibre.
//
// Two options, both open / non-proprietary (ARCHITECTURE P6 — MapLibre, no
// Mapbox). The app tries the external CARTO dark raster style first; if tiles
// fail to load (e.g. blocked network in a demo environment), it transparently
// falls back to a self-contained solid + graticule style so the map ALWAYS
// renders something coherent (ARCHITECTURE P7 — demo reliability).

import type { StyleSpecification } from "maplibre-gl";

const MISSION_BG = "#070b14"; // deep navy "mission control" backdrop
const GRATICULE = "#16324f";
const GRATICULE_MAJOR = "#1f4a70";

/**
 * External dark basemap using CARTO's free dark_nolabels raster tiles.
 * CARTO basemaps are free for use with attribution and are a common open
 * choice with MapLibre.
 */
export function cartoDarkStyle(): StyleSpecification {
  return {
    version: 8,
    name: "carto-dark",
    glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
    sources: {
      "carto-dark": {
        type: "raster",
        tiles: [
          "https://a.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png",
          "https://b.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png",
          "https://c.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png",
        ],
        tileSize: 256,
        attribution:
          '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, © <a href="https://carto.com/attributions">CARTO</a>',
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": MISSION_BG } },
      {
        id: "carto-dark",
        type: "raster",
        source: "carto-dark",
        paint: { "raster-opacity": 0.9, "raster-fade-duration": 200 },
      },
    ],
  };
}

/**
 * Build a graticule (lon/lat grid) GeoJSON over a bbox so the offline fallback
 * still conveys geographic context.
 */
export function graticuleGeoJSON(
  bbox: [number, number, number, number],
  stepMinor = 1,
  stepMajor = 5
): GeoJSON.FeatureCollection {
  const [w, s, e, n] = bbox;
  // pad a little beyond the data bbox so lines extend past the region
  const pad = 4;
  const W = Math.floor((w - pad) / stepMinor) * stepMinor;
  const E = Math.ceil((e + pad) / stepMinor) * stepMinor;
  const S = Math.floor((s - pad) / stepMinor) * stepMinor;
  const N = Math.ceil((n + pad) / stepMinor) * stepMinor;
  const features: GeoJSON.Feature[] = [];
  for (let lon = W; lon <= E + 1e-9; lon += stepMinor) {
    features.push({
      type: "Feature",
      properties: { major: Math.abs(lon % stepMajor) < 1e-9 },
      geometry: {
        type: "LineString",
        coordinates: [
          [lon, S],
          [lon, N],
        ],
      },
    });
  }
  for (let lat = S; lat <= N + 1e-9; lat += stepMinor) {
    features.push({
      type: "Feature",
      properties: { major: Math.abs(lat % stepMajor) < 1e-9 },
      geometry: {
        type: "LineString",
        coordinates: [
          [W, lat],
          [E, lat],
        ],
      },
    });
  }
  return { type: "FeatureCollection", features };
}

/** Self-contained offline fallback style — no external tiles. */
export function offlineGraticuleStyle(
  bbox: [number, number, number, number]
): StyleSpecification {
  return {
    version: 8,
    name: "offline-graticule",
    sources: {
      graticule: {
        type: "geojson",
        data: graticuleGeoJSON(bbox) as unknown as GeoJSON.GeoJSON,
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": MISSION_BG } },
      {
        id: "graticule-minor",
        type: "line",
        source: "graticule",
        filter: ["!", ["get", "major"]],
        paint: { "line-color": GRATICULE, "line-width": 0.5, "line-opacity": 0.6 },
      },
      {
        id: "graticule-major",
        type: "line",
        source: "graticule",
        filter: ["get", "major"],
        paint: { "line-color": GRATICULE_MAJOR, "line-width": 1, "line-opacity": 0.8 },
      },
    ],
  };
}
