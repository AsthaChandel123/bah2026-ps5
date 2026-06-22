"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef } from "react";
import { useStore } from "@/lib/store";
import { dataApi } from "@/lib/api";
import Header from "@/components/Header";
import LeftRail from "@/components/LeftRail";
import Legend from "@/components/Legend";
import BottomTimeline from "@/components/BottomTimeline";
import ChartDock from "@/components/ChartDock";
import Drawer from "@/components/Drawer";

// Map must be client-only (WebGL needs window) — ARCHITECTURE §9 risk note.
const MapStage = dynamic(() => import("@/components/MapStage"), {
  ssr: false,
  loading: () => (
    <div className="overlay">
      <div className="spinner" />
      <div className="msg">Initializing map engine…</div>
    </div>
  ),
});

export default function Dashboard() {
  const status = useStore((s) => s.status);
  const error = useStore((s) => s.error);
  const setData = useStore((s) => s.setData);
  const setStatus = useStore((s) => s.setStatus);

  const playing = useStore((s) => s.playing);
  const playbackSpeed = useStore((s) => s.playbackSpeed);
  const stepTime = useStore((s) => s.stepTime);

  // ---- Load all artifacts once ----
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setStatus("loading");
      try {
        // metadata + fields are required; the rest are best-effort.
        const [metadata, fields] = await Promise.all([
          dataApi.metadata(),
          dataApi.fieldsDaily(),
        ]);
        if (cancelled) return;
        setData({ metadata, fields });

        const optional = await Promise.allSettled([
          dataApi.climatology(),
          dataApi.uncertainty(),
          dataApi.scenarios(),
          dataApi.sources(),
          dataApi.metrics(),
          dataApi.forecast(),
        ]);
        if (cancelled) return;
        const [clim, unc, scen, src, met, fc] = optional;
        setData({
          climatology: clim.status === "fulfilled" ? clim.value : null,
          uncertainty: unc.status === "fulfilled" ? unc.value : null,
          scenarios: scen.status === "fulfilled" ? scen.value : null,
          sources: src.status === "fulfilled" ? src.value : null,
          metrics: met.status === "fulfilled" ? met.value : null,
          forecast: fc.status === "fulfilled" ? fc.value : null,
        });
        setStatus("ready");
      } catch (e) {
        if (cancelled) return;
        setStatus(
          "error",
          e instanceof Error ? e.message : "Failed to load climate data."
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [setData, setStatus]);

  // ---- Single requestAnimationFrame clock drives the timeline ----
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number>(0);
  useEffect(() => {
    if (!playing) {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      return;
    }
    const loop = (now: number) => {
      const interval = 1000 / Math.max(1, playbackSpeed);
      if (now - lastTickRef.current >= interval) {
        lastTickRef.current = now;
        stepTime(1);
      }
      rafRef.current = requestAnimationFrame(loop);
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [playing, playbackSpeed, stepTime]);

  // ---- Keyboard shortcuts (space=play, arrows=step) ----
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.code === "Space") {
        e.preventDefault();
        useStore.getState().togglePlaying();
      } else if (e.code === "ArrowRight") {
        e.preventDefault();
        useStore.getState().stepTime(1);
      } else if (e.code === "ArrowLeft") {
        e.preventDefault();
        useStore.getState().stepTime(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <main className="app">
      <Header />
      <div className="stage">
        <MapStage />
        {status === "ready" && (
          <>
            <LeftRail />
            <Legend />
            <ChartDock />
            <BottomTimeline />
          </>
        )}
        <Drawer />

        {status !== "ready" && status !== "error" && (
          <div className="overlay">
            <div className="spinner" />
            <div className="msg">Loading climate twin data…</div>
          </div>
        )}
        {status === "error" && (
          <div className="overlay">
            <div className="err">
              Failed to load data.
              <br />
              {error}
              <br />
              <br />
              Run <span className="kbd">npm run gen:data</span> to generate
              sample data, then reload.
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
