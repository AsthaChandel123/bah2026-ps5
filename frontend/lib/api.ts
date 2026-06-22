// Typed data-access layer.
//
// Default: read static JSON from `/data/*.json` (frontend/public/data).
// If NEXT_PUBLIC_API_BASE is set, fetch from the backend instead (same schema).
//
// Two URL conventions are supported transparently:
//   • static mode (no API base)  -> `/data/<file>.json`
//   • API mode (NEXT_PUBLIC_API_BASE, e.g. http://host/api)
//       -> the FastAPI service exposes each artifact at a *namespaced* path
//          without the `.json` suffix: `/api/metadata`, `/api/fields_daily`,
//          …, `/api/forecast` (see backend/app/routes). We therefore request
//          `${API_BASE}/<name>` (no `.json`) in this mode.
// Endpoint paths follow ARCHITECTURE §10; for the PoC we read whole artifacts
// client-side (the grid is tiny — ARCHITECTURE §9.1).

import type {
  Metadata,
  FieldsDaily,
  Climatology,
  Uncertainty,
  Scenarios,
  Sources,
  Metrics,
  Forecast,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

/** Logical artifact name (no extension) → its static `/data` filename. */
type ArtifactName =
  | "metadata"
  | "fields_daily"
  | "climatology"
  | "uncertainty"
  | "scenarios"
  | "sources"
  | "metrics"
  | "forecast";

/** Where to read a given artifact from.
 *  - API mode: `${API_BASE}/<name>` (backend serves namespaced, no `.json`).
 *  - static mode: `/data/<name>.json`. */
function urlFor(name: ArtifactName): string {
  if (API_BASE) return `${API_BASE}/${name}`;
  return `/data/${name}.json`;
}

async function getJson<T>(name: ArtifactName): Promise<T> {
  const res = await fetch(urlFor(name), { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to load ${name}: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

/** Forecast is special: the backend wraps it as `{available, forecast}` (HTTP
 *  200 even when absent), whereas the static file is the raw artifact. Normalise
 *  both to `Forecast | null`. */
async function getForecast(): Promise<Forecast | null> {
  const res = await fetch(urlFor("forecast"), { cache: "no-store" });
  if (!res.ok) return null; // e.g. no static forecast.json present
  const body = (await res.json()) as
    | Forecast
    | { available: boolean; forecast?: Forecast };
  if (body && typeof body === "object" && "available" in body) {
    return body.available && body.forecast ? body.forecast : null;
  }
  return body as Forecast;
}

export const dataApi = {
  base: API_BASE || "/data (static)",
  metadata: () => getJson<Metadata>("metadata"),
  fieldsDaily: () => getJson<FieldsDaily>("fields_daily"),
  climatology: () => getJson<Climatology>("climatology"),
  uncertainty: () => getJson<Uncertainty>("uncertainty"),
  scenarios: () => getJson<Scenarios>("scenarios"),
  sources: () => getJson<Sources>("sources"),
  metrics: () => getJson<Metrics>("metrics"),
  forecast: () => getForecast(),
};

export type DataApi = typeof dataApi;
