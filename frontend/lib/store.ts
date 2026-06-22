// Zustand store — central UI + data state for the dashboard.
// Holds the required interaction state {variable, timeIndex, playing, scenario,
// selectedCell, comparing} plus the loaded climate artifacts and load status.

import { create } from "zustand";
import type {
  BaseVariableKey,
  Climatology,
  FieldsDaily,
  Forecast,
  Metadata,
  Metrics,
  Scenarios,
  ScenarioState,
  SelectedCell,
  Sources,
  Uncertainty,
  VariableKey,
} from "./types";
import { BASELINE_SCENARIO } from "./types";

export type LoadStatus = "idle" | "loading" | "ready" | "error";
export type RegionKey = "marathwada" | "kerala";

interface AppData {
  metadata: Metadata | null;
  fields: FieldsDaily | null;
  climatology: Climatology | null;
  uncertainty: Uncertainty | null;
  scenarios: Scenarios | null;
  sources: Sources | null;
  metrics: Metrics | null;
  forecast: Forecast | null;
}

interface AppState extends AppData {
  status: LoadStatus;
  error: string | null;

  // --- required interaction state ---
  variable: VariableKey;
  timeIndex: number;
  playing: boolean;
  playbackSpeed: number; // timesteps per second
  scenario: ScenarioState;
  selectedCell: SelectedCell | null;
  comparing: boolean; // before/after compare mode

  // --- ancillary UI state ---
  region: RegionKey;
  opacity: number; // 0..1 field opacity
  showHexAggregation: boolean;
  showForecast: boolean; // show the 7-day forecast card in the chart dock
  activePanel: "layers" | "whatif" | "sources" | "metrics" | "about" | null;

  // --- actions ---
  setData: (d: Partial<AppData>) => void;
  setStatus: (s: LoadStatus, error?: string | null) => void;
  setVariable: (v: VariableKey) => void;
  setTimeIndex: (t: number) => void;
  stepTime: (delta: number) => void;
  setPlaying: (p: boolean) => void;
  togglePlaying: () => void;
  setPlaybackSpeed: (s: number) => void;
  setScenario: (s: Partial<ScenarioState>) => void;
  applyScenario: (s: ScenarioState) => void;
  resetScenario: () => void;
  setSelectedCell: (c: SelectedCell | null) => void;
  setComparing: (c: boolean) => void;
  toggleComparing: () => void;
  setRegion: (r: RegionKey) => void;
  setOpacity: (o: number) => void;
  setShowHexAggregation: (b: boolean) => void;
  setShowForecast: (b: boolean) => void;
  toggleForecast: () => void;
  setActivePanel: (p: AppState["activePanel"]) => void;
}

/** The base (field-backed) variable used for rendering/charts. "uncertainty"
 * is a derived view that colors the uncertainty of the last base variable. */
export function baseVariableOf(v: VariableKey): BaseVariableKey {
  return v === "uncertainty" ? "rainfall" : v;
}

export const useStore = create<AppState>((set, get) => ({
  metadata: null,
  fields: null,
  climatology: null,
  uncertainty: null,
  scenarios: null,
  sources: null,
  metrics: null,
  forecast: null,

  status: "idle",
  error: null,

  variable: "rainfall",
  timeIndex: 0,
  playing: false,
  playbackSpeed: 12,
  scenario: { ...BASELINE_SCENARIO },
  selectedCell: null,
  comparing: false,

  region: "marathwada",
  opacity: 0.85,
  showHexAggregation: false,
  showForecast: false,
  activePanel: "layers",

  setData: (d) => set((s) => ({ ...s, ...d })),
  setStatus: (status, error = null) => set({ status, error }),
  setVariable: (variable) => set({ variable }),
  setTimeIndex: (timeIndex) => {
    const n = get().metadata?.time.n ?? get().fields?.dates.length ?? 1;
    set({ timeIndex: Math.max(0, Math.min(n - 1, Math.round(timeIndex))) });
  },
  stepTime: (delta) => {
    const n = get().metadata?.time.n ?? get().fields?.dates.length ?? 1;
    const next = (get().timeIndex + delta + n) % n;
    set({ timeIndex: next });
  },
  setPlaying: (playing) => set({ playing }),
  togglePlaying: () => set((s) => ({ playing: !s.playing })),
  setPlaybackSpeed: (playbackSpeed) => set({ playbackSpeed }),
  setScenario: (s) => set((st) => ({ scenario: { ...st.scenario, ...s } })),
  applyScenario: (scenario) => set({ scenario }),
  resetScenario: () => set({ scenario: { ...BASELINE_SCENARIO } }),
  setSelectedCell: (selectedCell) => set({ selectedCell }),
  setComparing: (comparing) => set({ comparing }),
  toggleComparing: () => set((s) => ({ comparing: !s.comparing })),
  setRegion: (region) => set({ region }),
  setOpacity: (opacity) => set({ opacity }),
  setShowHexAggregation: (showHexAggregation) => set({ showHexAggregation }),
  setShowForecast: (showForecast) => set({ showForecast }),
  toggleForecast: () => set((s) => ({ showForecast: !s.showForecast })),
  setActivePanel: (activePanel) => set({ activePanel }),
}));
