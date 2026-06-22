"use client";

import { useStore } from "@/lib/store";

function fmt(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") return v.toFixed(2);
  return String(v);
}

export default function MetricsPanel() {
  const metrics = useStore((s) => s.metrics);

  const hasModels = metrics && metrics.models && metrics.models.length > 0;

  if (!metrics || (!hasModels && !metrics.ensemble)) {
    return (
      <div>
        <div className="empty-hint">
          No metrics yet.
          <br />
          models/evaluate.py writes RMSE/MAE/CSI etc. here (ARCHITECTURE §15),
          validated against held-out IMD observations with a leakage-free CV
          protocol (rolling + spatially-blocked + leave-one-monsoon-out).
        </div>
      </div>
    );
  }

  const ens = (metrics.ensemble ?? {}) as Record<string, Record<string, unknown>>;
  const ensVars = Object.keys(ens).filter(
    (k) => typeof ens[k] === "object" && ens[k] !== null
  );

  return (
    <div>
      <p className="help-line" style={{ marginTop: 0 }}>
        {metrics.note ??
          "Calibrated ensemble (stacking + EMOS + conformal). Lower RMSE/MAE/CRPS is better; higher CSI is better."}
      </p>

      {hasModels && (
        <>
          <div className="panel-title" style={{ marginTop: 16 }}>
            Base learners
          </div>
          <table className="dtable">
            <thead>
              <tr>
                <th>Model</th>
                <th>Variable</th>
                <th>RMSE</th>
                <th>MAE</th>
                <th>CSI</th>
              </tr>
            </thead>
            <tbody>
              {metrics.models.map((m, k) => (
                <tr key={k}>
                  <td style={{ color: "var(--text-0)" }}>{m.name}</td>
                  <td>{m.var}</td>
                  <td style={{ fontFamily: "var(--mono)" }}>{fmt(m.RMSE)}</td>
                  <td style={{ fontFamily: "var(--mono)" }}>{fmt(m.MAE)}</td>
                  <td style={{ fontFamily: "var(--mono)" }}>{fmt(m.CSI)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {ensVars.length > 0 && (
        <>
          <div className="panel-title" style={{ marginTop: 20 }}>
            Fused ensemble{ens.method ? ` · ${String(ens.method)}` : ""}
          </div>
          <table className="dtable">
            <thead>
              <tr>
                <th>Variable</th>
                <th>RMSE</th>
                <th>MAE</th>
                <th>CRPS</th>
                <th>CSI</th>
                <th>Cov₉₀</th>
              </tr>
            </thead>
            <tbody>
              {ensVars.map((v) => {
                const row = ens[v];
                return (
                  <tr key={v}>
                    <td style={{ color: "var(--text-0)" }}>{v}</td>
                    <td style={{ fontFamily: "var(--mono)" }}>{fmt(row.RMSE)}</td>
                    <td style={{ fontFamily: "var(--mono)" }}>{fmt(row.MAE)}</td>
                    <td style={{ fontFamily: "var(--mono)" }}>{fmt(row.CRPS)}</td>
                    <td style={{ fontFamily: "var(--mono)" }}>{fmt(row.CSI)}</td>
                    <td style={{ fontFamily: "var(--mono)" }}>
                      {fmt(row.coverage_90)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}

      {metrics.baselines && (
        <p className="help-line" style={{ marginTop: 16 }}>
          Skill is always reported against persistence + climatology baselines
          (ARCHITECTURE §15.2).
        </p>
      )}
    </div>
  );
}
