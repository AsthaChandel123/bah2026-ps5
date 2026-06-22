"use client";

import { useStore } from "@/lib/store";
import SourcesPanel from "@/components/SourcesPanel";
import MetricsPanel from "@/components/MetricsPanel";
import AboutPanel from "@/components/AboutPanel";

export default function Drawer() {
  const activePanel = useStore((s) => s.activePanel);
  const setActivePanel = useStore((s) => s.setActivePanel);

  const isDrawer =
    activePanel === "sources" ||
    activePanel === "metrics" ||
    activePanel === "about";
  if (!isDrawer) return null;

  const title =
    activePanel === "sources"
      ? "Data Sources"
      : activePanel === "metrics"
      ? "Model Performance"
      : "About the Digital Twin";

  // Return to the Layers panel when the drawer closes.
  const close = () => setActivePanel("layers");

  return (
    <>
      <div className="drawer-backdrop" onClick={close} />
      <aside className="drawer" role="dialog" aria-label={title}>
        <div className="drawer-head">
          <h2>{title}</h2>
          <button className="close-x" onClick={close} aria-label="Close">
            ×
          </button>
        </div>
        <div className="drawer-body">
          {activePanel === "sources" && <SourcesPanel />}
          {activePanel === "metrics" && <MetricsPanel />}
          {activePanel === "about" && <AboutPanel />}
        </div>
      </aside>
    </>
  );
}
