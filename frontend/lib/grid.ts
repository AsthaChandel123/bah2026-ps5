// Grid geometry helpers — map between (lat,lon) and grid indices, and build the
// polygon cells for deck.gl rendering.

import type { GridMeta, SelectedCell } from "./types";

/** Find the nearest grid cell index to a clicked (lon,lat). */
export function nearestCell(
  grid: GridMeta,
  lon: number,
  lat: number
): SelectedCell | null {
  const { lats, lons } = grid;
  if (!lats.length || !lons.length) return null;
  let bi = 0;
  let bestLat = Infinity;
  for (let i = 0; i < lats.length; i++) {
    const d = Math.abs(lats[i] - lat);
    if (d < bestLat) {
      bestLat = d;
      bi = i;
    }
  }
  let bj = 0;
  let bestLon = Infinity;
  for (let j = 0; j < lons.length; j++) {
    const d = Math.abs(lons[j] - lon);
    if (d < bestLon) {
      bestLon = d;
      bj = j;
    }
  }
  return { i: bi, j: bj, lat: lats[bi], lon: lons[bj] };
}

/** Center [lon,lat] of the grid bbox, for initial map view. */
export function gridCenter(grid: GridMeta): [number, number] {
  const lat = (grid.lats[0] + grid.lats[grid.lats.length - 1]) / 2;
  const lon = (grid.lons[0] + grid.lons[grid.lons.length - 1]) / 2;
  return [lon, lat];
}

/** Cell polygon (square in lon/lat) for a given index, as a deck.gl polygon. */
export function cellPolygon(
  grid: GridMeta,
  i: number,
  j: number
): [number, number][] {
  const h = grid.res_deg / 2;
  const lat = grid.lats[i];
  const lon = grid.lons[j];
  return [
    [lon - h, lat - h],
    [lon + h, lat - h],
    [lon + h, lat + h],
    [lon - h, lat + h],
  ];
}
