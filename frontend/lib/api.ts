// Typed data-access layer.
//
// Default: read static JSON from `/data/*.json` (frontend/public/data).
// If NEXT_PUBLIC_API_BASE is set, fetch from the backend instead (same schema).
// Endpoint paths follow ARCHITECTURE §10 where applicable; for the PoC we read
// whole artifacts client-side (the grid is tiny — ARCHITECTURE §9.1).

import type {
  Metadata,
  FieldsDaily,
  Climatology,
  Uncertainty,
  Scenarios,
  Sources,
  Metrics,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

/** Where to read a given artifact from. When API_BASE is set we still default
 * to its /data convention but allow a backend to serve the same filenames. */
function urlFor(file: string): string {
  if (API_BASE) return `${API_BASE}/${file}`;
  return `/data/${file}`;
}

async function getJson<T>(file: string): Promise<T> {
  const res = await fetch(urlFor(file), { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load ${file}: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export const dataApi = {
  base: API_BASE || "/data (static)",
  metadata: () => getJson<Metadata>("metadata.json"),
  fieldsDaily: () => getJson<FieldsDaily>("fields_daily.json"),
  climatology: () => getJson<Climatology>("climatology.json"),
  uncertainty: () => getJson<Uncertainty>("uncertainty.json"),
  scenarios: () => getJson<Scenarios>("scenarios.json"),
  sources: () => getJson<Sources>("sources.json"),
  metrics: () => getJson<Metrics>("metrics.json"),
};

export type DataApi = typeof dataApi;
