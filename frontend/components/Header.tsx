"use client";

import { useStore, type RegionKey } from "@/lib/store";

const REGIONS: { id: RegionKey; label: string; available: boolean }[] = [
  { id: "marathwada", label: "Marathwada", available: true },
  { id: "kerala", label: "Kerala / W. Ghats", available: false },
];

export default function Header() {
  const region = useStore((s) => s.region);
  const setRegion = useStore((s) => s.setRegion);
  const activePanel = useStore((s) => s.activePanel);
  const setActivePanel = useStore((s) => s.setActivePanel);
  const metadata = useStore((s) => s.metadata);
  const apiBase = process.env.NEXT_PUBLIC_API_BASE;

  return (
    <header className="header">
      <div className="brand">
        <div className="logo" aria-hidden />
        <div style={{ minWidth: 0 }}>
          <div className="title">Bharat Climate Twin</div>
          <div className="subtitle">
            AI-Powered Digital Twin of India&rsquo;s Climate
          </div>
        </div>
      </div>

      <div className="ps-badge">ISRO BAH 2026 · PS5</div>

      <div style={{ width: 8 }} />

      <label className="chip" style={{ gap: 8 }}>
        <span style={{ color: "var(--text-2)", fontSize: 11 }}>Region</span>
        <select
          className="input"
          value={region}
          onChange={(e) => {
            const r = e.target.value as RegionKey;
            const meta = REGIONS.find((x) => x.id === r);
            if (meta && !meta.available) {
              // Secondary pilot is a documented "future" region (ARCHITECTURE §3.2).
              alert(
                "Kerala / Western Ghats is the secondary pilot (future). " +
                  "The same pipeline + UI scales to it — only the data bbox changes."
              );
              return;
            }
            setRegion(r);
          }}
        >
          {REGIONS.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
              {r.available ? "" : " (future)"}
            </option>
          ))}
        </select>
      </label>

      <div className="spacer" />

      {apiBase ? (
        <span
          className="chip"
          title={`Data served from backend: ${apiBase}`}
          style={{ color: "var(--good)" }}
        >
          <span className="dot" style={{ background: "var(--good)" }} />
          live backend
        </span>
      ) : (
        <span
          className="chip"
          title="Reading static JSON from /data"
          style={{ color: "var(--text-2)" }}
        >
          <span className="dot" style={{ background: "var(--text-2)" }} />
          static data
        </span>
      )}

      {metadata?.generator?.includes("sample") && (
        <span
          className="chip"
          title={metadata.notes}
          style={{ color: "var(--accent-warm)" }}
        >
          <span className="dot" style={{ background: "var(--accent-warm)" }} />
          sample
        </span>
      )}

      <div className="seg" role="group" aria-label="Panels">
        <button
          className={activePanel === "sources" ? "active" : ""}
          onClick={() =>
            setActivePanel(activePanel === "sources" ? null : "sources")
          }
        >
          Data Sources
        </button>
        <button
          className={activePanel === "metrics" ? "active" : ""}
          onClick={() =>
            setActivePanel(activePanel === "metrics" ? null : "metrics")
          }
        >
          Model Perf.
        </button>
        <button
          className={activePanel === "about" ? "active" : ""}
          onClick={() =>
            setActivePanel(activePanel === "about" ? null : "about")
          }
        >
          About
        </button>
      </div>
    </header>
  );
}
