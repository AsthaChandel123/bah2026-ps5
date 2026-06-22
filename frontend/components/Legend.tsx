"use client";

import { useMemo } from "react";
import { useStore, baseVariableOf } from "@/lib/store";
import {
  colormapGradientCss,
  legendTicks,
} from "@/lib/colormaps";
import type { ColormapName } from "@/lib/types";

export default function Legend() {
  const metadata = useStore((s) => s.metadata);
  const uncertainty = useStore((s) => s.uncertainty);
  const variable = useStore((s) => s.variable);
  const baseVar = baseVariableOf(variable);
  const isUnc = variable === "uncertainty";

  const { cmap, vmin, vmax, label, units } = useMemo(() => {
    if (!metadata)
      return {
        cmap: "temp" as ColormapName,
        vmin: 0,
        vmax: 1,
        label: "",
        units: "",
      };
    if (isUnc) {
      // `variables.uncertainty` is optional in the metadata contract.
      let vmax = metadata.variables.uncertainty?.vmax ?? 10;
      const unc = uncertainty?.[baseVar];
      if (unc) {
        let m = 0;
        for (const row of unc) for (const v of row) if (v > m) m = v;
        vmax = Math.max(1, Math.ceil(m));
      }
      return {
        cmap: "uncertainty" as ColormapName,
        vmin: 0,
        vmax,
        label: `Uncertainty · ${metadata.variables[baseVar].label}`,
        units: `± ${metadata.variables[baseVar].units} (1σ)`,
      };
    }
    const v = metadata.variables[baseVar];
    return { cmap: v.cmap, vmin: v.vmin, vmax: v.vmax, label: v.label, units: v.units };
  }, [metadata, isUnc, baseVar, uncertainty]);

  if (!metadata) return null;
  const ticks = legendTicks(vmin, vmax, 5);
  const digits = baseVar === "rainfall" && !isUnc ? 0 : isUnc ? 1 : 0;

  return (
    <div className="legend panel">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600 }}>{label}</span>
        <span
          className="dot"
          style={{
            background:
              cmap === "rain"
                ? "var(--rain)"
                : cmap === "temp"
                ? "var(--temp)"
                : "var(--accent-warm)",
          }}
        />
      </div>
      <div className="bar" style={{ background: colormapGradientCss(cmap) }} />
      <div className="ticks">
        {ticks.map((t, k) => (
          <span key={k}>{t.toFixed(digits)}</span>
        ))}
      </div>
      <div className="units">{units}</div>
    </div>
  );
}
