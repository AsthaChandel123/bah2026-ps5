// Colormaps for the climate fields.
// Accessible, perceptually-reasonable ramps following the contract:
//   rain:        white → blue → purple
//   temp:        blue → cyan → yellow → red
//   uncertainty: dark teal → amber → magenta (a distinct "alert" ramp)
//
// We expose:
//   - colormapStops(): CSS gradient stops (for the Legend component)
//   - sampleColormap(): value→RGBA, used by deck.gl layers (JS colormap; the
//     grids are tiny so per-cell JS sampling is instant, the ARCHITECTURE
//     "GPU colormap" pattern is approximated for GridCellLayer fill colors).

import type { ColormapName } from "./types";

export type RGB = [number, number, number];
export type RGBA = [number, number, number, number];

// Anchor stops: position (0..1) → RGB.
interface Stop {
  t: number;
  c: RGB;
}

const RAMPS: Record<ColormapName, Stop[]> = {
  // white → light blue → blue → indigo → purple
  rain: [
    { t: 0.0, c: [247, 251, 255] },
    { t: 0.15, c: [198, 219, 239] },
    { t: 0.35, c: [107, 174, 214] },
    { t: 0.55, c: [49, 130, 189] },
    { t: 0.75, c: [55, 70, 190] },
    { t: 0.9, c: [106, 47, 168] },
    { t: 1.0, c: [74, 20, 134] },
  ],
  // blue → cyan → green-yellow → yellow → orange → red
  temp: [
    { t: 0.0, c: [49, 54, 149] },
    { t: 0.2, c: [69, 117, 180] },
    { t: 0.38, c: [116, 173, 209] },
    { t: 0.5, c: [224, 243, 248] },
    { t: 0.62, c: [254, 224, 144] },
    { t: 0.8, c: [244, 109, 67] },
    { t: 1.0, c: [165, 0, 38] },
  ],
  // dark teal → green → amber → magenta (distinct from rain/temp)
  uncertainty: [
    { t: 0.0, c: [12, 44, 52] },
    { t: 0.3, c: [21, 101, 112] },
    { t: 0.55, c: [120, 160, 90] },
    { t: 0.75, c: [240, 180, 60] },
    { t: 1.0, c: [200, 60, 150] },
  ],
};

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/** Sample a colormap at normalized position f∈[0,1] → RGB. */
export function sampleRamp(name: ColormapName, f: number): RGB {
  const stops = RAMPS[name] ?? RAMPS.temp;
  const x = Math.min(1, Math.max(0, f));
  for (let k = 0; k < stops.length - 1; k++) {
    const s0 = stops[k];
    const s1 = stops[k + 1];
    if (x >= s0.t && x <= s1.t) {
      const tt = s1.t === s0.t ? 0 : (x - s0.t) / (s1.t - s0.t);
      return [
        Math.round(lerp(s0.c[0], s1.c[0], tt)),
        Math.round(lerp(s0.c[1], s1.c[1], tt)),
        Math.round(lerp(s0.c[2], s1.c[2], tt)),
      ];
    }
  }
  return stops[stops.length - 1].c;
}

/**
 * Map a raw value to RGBA given a colormap + range.
 * Values at/below vmin (e.g. dry days for rain) become transparent so the
 * basemap shows through — the classic weather-map look.
 */
export function sampleColormap(
  name: ColormapName,
  value: number,
  vmin: number,
  vmax: number,
  opts?: { transparentBelow?: number; maxAlpha?: number }
): RGBA {
  const maxAlpha = opts?.maxAlpha ?? 220;
  const span = vmax - vmin || 1;
  const f = (value - vmin) / span;

  // Rain (and uncertainty) fade to transparent near the bottom of the range so
  // dry/low cells don't paint a solid sheet over the map.
  const transparentBelow = opts?.transparentBelow;
  if (transparentBelow !== undefined && value <= transparentBelow) {
    return [255, 255, 255, 0];
  }

  const [r, g, b] = sampleRamp(name, f);

  let alpha = maxAlpha;
  if (name === "rain") {
    // Ramp alpha up over the low end for a soft edge on light rain.
    alpha = Math.round(Math.min(maxAlpha, 40 + f * 320));
  } else if (name === "uncertainty") {
    alpha = Math.round(Math.min(maxAlpha, 60 + f * 260));
  }
  return [r, g, b, Math.max(0, Math.min(255, alpha))];
}

/** CSS linear-gradient string for the legend bar. */
export function colormapGradientCss(name: ColormapName): string {
  const stops = RAMPS[name] ?? RAMPS.temp;
  const parts = stops.map(
    (s) => `rgb(${s.c[0]},${s.c[1]},${s.c[2]}) ${Math.round(s.t * 100)}%`
  );
  return `linear-gradient(90deg, ${parts.join(", ")})`;
}

/** Discrete tick labels for a legend, evenly spaced across [vmin,vmax]. */
export function legendTicks(vmin: number, vmax: number, n = 5): number[] {
  const out: number[] = [];
  for (let k = 0; k < n; k++) {
    out.push(vmin + ((vmax - vmin) * k) / (n - 1));
  }
  return out;
}
