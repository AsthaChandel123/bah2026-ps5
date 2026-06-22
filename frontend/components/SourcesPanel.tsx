"use client";

import { useMemo } from "react";
import { useStore } from "@/lib/store";

const INDIAN_PROVIDERS = ["IMD", "ISRO", "NRSC", "NCMRWF", "MoWR", "MOSDAC"];

function isIndian(provider: string): boolean {
  return INDIAN_PROVIDERS.some((p) => provider.toUpperCase().includes(p));
}
function isAnchor(role: string): boolean {
  return role.toUpperCase().includes("ANCHOR");
}

export default function SourcesPanel() {
  const sources = useStore((s) => s.sources);

  const stats = useMemo(() => {
    const list = sources?.sources ?? [];
    const indian = list.filter((s) => isIndian(s.provider)).length;
    const types = new Set(list.map((s) => s.type)).size;
    return { total: list.length, indian, types };
  }, [sources]);

  if (!sources || sources.sources.length === 0) {
    return (
      <div className="empty-hint">
        No sources.json found. The data-foundation worker drops the consolidated
        30+ source catalogue here (ARCHITECTURE §4.1).
      </div>
    );
  }

  return (
    <div>
      <p className="help-line" style={{ marginTop: 0 }}>
        {sources.note ??
          "Multi-source fusion — no variable is ever served from a single sensor (ARCHITECTURE P1)."}
      </p>

      <div style={{ display: "flex", gap: 10, margin: "14px 0 18px" }}>
        <StatBox k="Datasets" v={String(stats.total)} accent />
        <StatBox k="Indian-origin" v={String(stats.indian)} good />
        <StatBox k="Source types" v={String(stats.types)} />
      </div>

      <table className="dtable">
        <thead>
          <tr>
            <th>Dataset</th>
            <th>Role</th>
            <th>Res / cadence</th>
            <th>Provider</th>
            <th>Access</th>
          </tr>
        </thead>
        <tbody>
          {sources.sources.map((s, k) => (
            <tr key={k}>
              <td style={{ color: "var(--text-0)", fontWeight: 500 }}>
                {s.name}
                {isAnchor(s.role) && (
                  <span className="pill anchor" style={{ marginLeft: 6 }}>
                    anchor
                  </span>
                )}
              </td>
              <td>{s.role}</td>
              <td style={{ fontFamily: "var(--mono)", fontSize: 11 }}>{s.res}</td>
              <td>
                <span className={`pill ${isIndian(s.provider) ? "indian" : ""}`}>
                  {s.provider}
                </span>
              </td>
              <td style={{ fontFamily: "var(--mono)", fontSize: 11 }}>{s.access}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatBox({
  k,
  v,
  accent,
  good,
}: {
  k: string;
  v: string;
  accent?: boolean;
  good?: boolean;
}) {
  return (
    <div
      className="panel"
      style={{
        padding: "10px 14px",
        flex: 1,
        background: "var(--bg-1)",
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 24,
          fontWeight: 700,
          color: accent ? "var(--accent)" : good ? "var(--good)" : "var(--text-0)",
        }}
      >
        {v}
      </div>
      <div style={{ fontSize: 10, color: "var(--text-2)", textTransform: "uppercase", letterSpacing: 0.6 }}>
        {k}
      </div>
    </div>
  );
}
