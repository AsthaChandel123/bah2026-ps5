"use client";

import { useMemo } from "react";
import { useStore } from "@/lib/store";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function BottomTimeline() {
  const metadata = useStore((s) => s.metadata);
  const timeIndex = useStore((s) => s.timeIndex);
  const setTimeIndex = useStore((s) => s.setTimeIndex);
  const playing = useStore((s) => s.playing);
  const togglePlaying = useStore((s) => s.togglePlaying);
  const speed = useStore((s) => s.playbackSpeed);
  const setSpeed = useStore((s) => s.setPlaybackSpeed);

  const n = metadata?.time.n ?? 1;
  const dateStr = metadata?.time.dates?.[timeIndex] ?? "";

  const { dateLabel, monthLabel, doy } = useMemo(() => {
    if (!dateStr) return { dateLabel: "", monthLabel: "", doy: 0 };
    const d = new Date(dateStr + "T00:00:00Z");
    const day = d.getUTCDate();
    const mon = MONTHS[d.getUTCMonth()];
    const start = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const doy = Math.round((d.getTime() - start.getTime()) / 86400000) + 1;
    return {
      dateLabel: `${day} ${mon} ${d.getUTCFullYear()}`,
      monthLabel: mon,
      doy,
    };
  }, [dateStr]);

  // A subtle season tint behind the scrubber: monsoon JJAS highlighted.
  // Built once from the date axis.
  const seasonGradient = useMemo(() => {
    if (!metadata) return "transparent";
    const dates = metadata.time.dates;
    const stops: string[] = [];
    for (let k = 0; k < dates.length; k += Math.max(1, Math.floor(dates.length / 60))) {
      const m = new Date(dates[k] + "T00:00:00Z").getUTCMonth(); // 0..11
      const pct = (k / (dates.length - 1)) * 100;
      // monsoon (Jun–Sep => months 5..8) gets a blue tint, else faint
      const col =
        m >= 5 && m <= 8
          ? "rgba(80,150,230,0.55)"
          : m === 9
          ? "rgba(80,150,230,0.28)"
          : "rgba(120,160,210,0.10)";
      stops.push(`${col} ${pct.toFixed(1)}%`);
    }
    return `linear-gradient(90deg, ${stops.join(", ")})`;
  }, [metadata]);

  const isMonsoon = (() => {
    const d = new Date(dateStr + "T00:00:00Z");
    const m = d.getUTCMonth();
    return m >= 5 && m <= 8;
  })();

  return (
    <div className="timeline panel">
      <button
        className="play"
        onClick={togglePlaying}
        aria-label={playing ? "Pause" : "Play"}
        title={playing ? "Pause (Space)" : "Play (Space)"}
      >
        {playing ? "❚❚" : "▶"}
      </button>

      <div className="tl-main">
        <div className="tl-top">
          <span className="tl-date">
            {dateLabel}
            {isMonsoon && (
              <span
                style={{
                  marginLeft: 10,
                  fontSize: 10,
                  color: "rgba(120,180,250,0.95)",
                  fontFamily: "var(--mono)",
                  border: "1px solid rgba(120,180,250,0.4)",
                  borderRadius: 12,
                  padding: "2px 8px",
                }}
              >
                MONSOON
              </span>
            )}
          </span>
          <span className="tl-sub">
            day {doy} / 365 · {monthLabel}
          </span>
        </div>
        <div className="scrub-wrap">
          <div className="season-track" style={{ background: seasonGradient }} />
          <input
            type="range"
            min={0}
            max={n - 1}
            step={1}
            value={timeIndex}
            style={{ ["--fill" as string]: `${(timeIndex / (n - 1)) * 100}%` }}
            onChange={(e) => setTimeIndex(parseInt(e.target.value, 10))}
            aria-label="Timeline scrubber"
          />
        </div>
      </div>

      <div className="speed">
        <span>speed</span>
        <div className="seg">
          {[6, 12, 24, 48].map((sp) => (
            <button
              key={sp}
              className={speed === sp ? "active" : ""}
              onClick={() => setSpeed(sp)}
            >
              {sp === 6 ? "0.5×" : sp === 12 ? "1×" : sp === 24 ? "2×" : "4×"}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
