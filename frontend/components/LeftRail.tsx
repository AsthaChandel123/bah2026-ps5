"use client";

import { useStore } from "@/lib/store";
import LayerPanel from "@/components/LayerPanel";
import WhatIfPanel from "@/components/WhatIfPanel";

export default function LeftRail() {
  const activePanel = useStore((s) => s.activePanel);
  const setActivePanel = useStore((s) => s.setActivePanel);

  // The left rail shows Layers or What-if. Drawer panels (sources/metrics/about)
  // render separately; when one of those is open we keep the last rail tab.
  const railTab =
    activePanel === "whatif" ? "whatif" : "layers";

  return (
    <div className="leftrail">
      <div className="rail-tabs">
        <div className="seg" style={{ width: "100%" }}>
          <button
            className={railTab === "layers" ? "active" : ""}
            onClick={() => setActivePanel("layers")}
          >
            Layers
          </button>
          <button
            className={railTab === "whatif" ? "active" : ""}
            onClick={() => setActivePanel("whatif")}
          >
            What-If Engine
          </button>
        </div>
      </div>
      <div className="rail-content">
        {railTab === "layers" ? <LayerPanel /> : <WhatIfPanel />}
      </div>
    </div>
  );
}
