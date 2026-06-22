"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import maplibregl, { Map as MLMap } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { SolidPolygonLayer, PolygonLayer } from "@deck.gl/layers";
import type { Layer } from "@deck.gl/core";
import { useStore, baseVariableOf } from "@/lib/store";
import {
  cartoDarkStyle,
  offlineGraticuleStyle,
  graticuleGeoJSON,
} from "@/lib/basemap";
import { gridCenter, nearestCell, cellPolygon } from "@/lib/grid";
import { sampleColormap } from "@/lib/colormaps";
import {
  scenarioFieldAtTime,
  physicsFromScenarios,
  isBaseline,
} from "@/lib/whatif";
import type { BaseVariableKey } from "@/lib/types";

interface CellDatum {
  polygon: [number, number][];
  i: number;
  j: number;
  value: number;
}

interface HoverInfo {
  x: number;
  y: number;
  lat: number;
  lon: number;
  value: number;
}

/** Selected-cell highlight as a stroked PolygonLayer (mission-cyan outline). */
function selectedOutlineLayer(
  grid: import("@/lib/types").GridMeta,
  i: number,
  j: number
): PolygonLayer<{ polygon: [number, number][] }> {
  return new PolygonLayer<{ polygon: [number, number][] }>({
    id: "selected-outline",
    data: [{ polygon: cellPolygon(grid, i, j) }],
    getPolygon: (d) => d.polygon,
    getFillColor: [54, 197, 240, 28],
    getLineColor: [54, 197, 240, 255],
    stroked: true,
    filled: true,
    getLineWidth: 2,
    lineWidthUnits: "pixels",
    pickable: false,
  });
}

export default function MapStage() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MLMap | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [usingFallback, setUsingFallback] = useState(false);
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [swipeX, setSwipeX] = useState(0.5);
  const swipeDragRef = useRef(false);

  // ---- store selectors ----
  const metadata = useStore((s) => s.metadata);
  const fields = useStore((s) => s.fields);
  const uncertainty = useStore((s) => s.uncertainty);
  const scenarios = useStore((s) => s.scenarios);
  const variable = useStore((s) => s.variable);
  const timeIndex = useStore((s) => s.timeIndex);
  const scenario = useStore((s) => s.scenario);
  const opacity = useStore((s) => s.opacity);
  const comparing = useStore((s) => s.comparing);
  const selectedCell = useStore((s) => s.selectedCell);
  const setSelectedCell = useStore((s) => s.setSelectedCell);

  const baseVar = baseVariableOf(variable);
  const isUncertaintyView = variable === "uncertainty";
  const phys = useMemo(() => physicsFromScenarios(scenarios), [scenarios]);

  // ---------------------------------------------------------------------------
  // Initialize MapLibre with deck.gl interleaved overlay.
  // Try external CARTO tiles; if they error, swap to the offline graticule.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || !metadata) return;
    const [clon, clat] = gridCenter(metadata.grid);

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: cartoDarkStyle(),
      center: [clon, clat],
      zoom: 6.4,
      minZoom: 3,
      maxZoom: 11,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    });
    mapRef.current = map;

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-left");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

    const overlay = new MapboxOverlay({ interleaved: true, layers: [] });
    overlayRef.current = overlay;
    map.addControl(overlay as unknown as maplibregl.IControl);

    // Fallback: if external raster tiles fail, switch to offline style.
    let fellBack = false;
    const fallback = () => {
      if (fellBack) return;
      fellBack = true;
      setUsingFallback(true);
      try {
        map.setStyle(offlineGraticuleStyle(metadata.bbox));
      } catch {
        /* noop */
      }
    };
    // If no tiles have rendered shortly after load, assume blocked.
    const guard = setTimeout(() => {
      // `loaded()` true but no source tiles → likely blocked; check a source.
      const src = map.getSource("carto-dark");
      if (!src) fallback();
    }, 4000);

    map.on("error", (e) => {
      const msg = String((e as { error?: { message?: string } })?.error?.message ?? "");
      if (msg.toLowerCase().includes("tile") || msg.includes("Failed to fetch")) {
        fallback();
      }
    });

    map.on("load", () => {
      setMapReady(true);
    });

    return () => {
      clearTimeout(guard);
      try {
        overlay.finalize();
      } catch {
        /* noop */
      }
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metadata]);

  // Re-add a graticule overlay (deck-independent) once fallback style loads, so
  // even the fallback has subtle geographic context drawn by MapLibre itself.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !usingFallback || !metadata) return;
    const apply = () => {
      if (map.getSource("graticule")) return;
      try {
        map.addSource("graticule", {
          type: "geojson",
          data: graticuleGeoJSON(metadata.bbox) as unknown as GeoJSON.GeoJSON,
        });
        map.addLayer({
          id: "grat-min",
          type: "line",
          source: "graticule",
          filter: ["!", ["get", "major"]],
          paint: { "line-color": "#16324f", "line-width": 0.5, "line-opacity": 0.6 },
        });
        map.addLayer({
          id: "grat-maj",
          type: "line",
          source: "graticule",
          filter: ["get", "major"],
          paint: { "line-color": "#1f4a70", "line-width": 1, "line-opacity": 0.8 },
        });
      } catch {
        /* noop */
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("styledata", apply);
  }, [usingFallback, metadata]);

  // ---------------------------------------------------------------------------
  // Compute the field grid for the current variable / time / scenario.
  // Returns {cells, vmin, vmax, cmap} for the active (scenario) layer.
  // ---------------------------------------------------------------------------
  const buildCells = useCallback(
    (useScenario: boolean): { cells: CellDatum[] } => {
      if (!fields || !metadata) return { cells: [] };
      const grid = metadata.grid;
      const cells: CellDatum[] = [];

      if (isUncertaintyView) {
        // Color the per-cell uncertainty of the last base variable (static).
        const unc = uncertainty?.[baseVar as BaseVariableKey];
        for (let i = 0; i < grid.nlat; i++) {
          for (let j = 0; j < grid.nlon; j++) {
            const value = unc ? unc[i][j] : 0;
            cells.push({ polygon: cellPolygon(grid, i, j), i, j, value });
          }
        }
        return { cells };
      }

      const field =
        useScenario && !isBaseline(scenario)
          ? scenarioFieldAtTime(fields, baseVar, timeIndex, scenario, phys)
          : fields[baseVar][timeIndex];

      for (let i = 0; i < grid.nlat; i++) {
        for (let j = 0; j < grid.nlon; j++) {
          cells.push({
            polygon: cellPolygon(grid, i, j),
            i,
            j,
            value: field[i][j],
          });
        }
      }
      return { cells };
    },
    [fields, metadata, uncertainty, isUncertaintyView, baseVar, scenario, timeIndex, phys]
  );

  // colormap params for the active variable
  const cmapParams = useMemo(() => {
    if (!metadata) return { cmap: "temp" as const, vmin: 0, vmax: 1 };
    if (isUncertaintyView) {
      // scale uncertainty view to the base variable's uncertainty range.
      // `variables.uncertainty` is optional in metadata — derive vmax from the
      // uncertainty cube when present, else fall back to a sane default.
      let vmax = metadata.variables.uncertainty?.vmax ?? 10;
      const unc = uncertainty?.[baseVar as BaseVariableKey];
      if (unc) {
        let m = 0;
        for (const row of unc) for (const val of row) if (val > m) m = val;
        vmax = Math.max(1, Math.ceil(m));
      }
      return { cmap: "uncertainty" as const, vmin: 0, vmax };
    }
    const v = metadata.variables[baseVar];
    return { cmap: v.cmap, vmin: v.vmin, vmax: v.vmax };
  }, [metadata, isUncertaintyView, baseVar, uncertainty]);

  const colorFor = useCallback(
    (value: number): [number, number, number, number] => {
      const { cmap, vmin, vmax } = cmapParams;
      const transparentBelow =
        cmap === "rain" ? Math.max(0.2, vmax * 0.01) : undefined;
      const rgba = sampleColormap(cmap, value, vmin, vmax, {
        transparentBelow,
        maxAlpha: Math.round(230 * opacity),
      });
      return [rgba[0], rgba[1], rgba[2], Math.round(rgba[3] * opacity)];
    },
    [cmapParams, opacity]
  );

  // ---------------------------------------------------------------------------
  // Build deck.gl layers and push to the overlay whenever inputs change.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !mapReady || !metadata) return;
    // In compare mode (non-uncertainty), the dedicated split effect below owns
    // the overlay layers — skip here to avoid clobbering it.
    if (comparing && !isUncertaintyView) return;

    const { cells: scenarioCells } = buildCells(true);

    const layers: Layer[] = [];

    // Active (scenario) field layer.
    layers.push(
      new SolidPolygonLayer<CellDatum>({
        id: "field-active",
        data: scenarioCells,
        getPolygon: (d) => d.polygon,
        getFillColor: (d) => colorFor(d.value),
        pickable: true,
        autoHighlight: true,
        highlightColor: [255, 255, 255, 60],
        onClick: (info) => {
          const obj = info.object as CellDatum | undefined;
          if (obj && metadata) {
            const c = nearestCell(
              metadata.grid,
              metadata.grid.lons[obj.j],
              metadata.grid.lats[obj.i]
            );
            setSelectedCell(c);
          }
        },
        onHover: (info) => {
          const obj = info.object as CellDatum | undefined;
          if (obj && info.coordinate) {
            setHover({
              x: info.x,
              y: info.y,
              lat: metadata.grid.lats[obj.i],
              lon: metadata.grid.lons[obj.j],
              value: obj.value,
            });
          } else {
            setHover(null);
          }
        },
        updateTriggers: {
          getFillColor: [variable, timeIndex, scenario, opacity, cmapParams, isUncertaintyView],
        },
      })
    );

    // Selected-cell outline.
    if (selectedCell && metadata) {
      layers.push(selectedOutlineLayer(metadata.grid, selectedCell.i, selectedCell.j));
    }

    overlay.setProps({ layers });
  }, [
    mapReady,
    metadata,
    buildCells,
    colorFor,
    comparing,
    isUncertaintyView,
    selectedCell,
    setSelectedCell,
    variable,
    timeIndex,
    scenario,
    opacity,
    cmapParams,
  ]);

  // ---------------------------------------------------------------------------
  // Compare-mode swipe: clip the BASELINE layer to the left of the handle by
  // restyling the active layer's container via CSS clip on a second canvas is
  // complex with a single interleaved context; instead we toggle which field
  // each side shows by splitting horizontally using the map container clip.
  //
  // Practical approach: we render baseline full, then clip the ACTIVE field
  // layer's DOM overlay. Since deck shares MapLibre's canvas, we implement the
  // split by drawing baseline on the left half and scenario on the right half
  // using two SolidPolygonLayers filtered by longitude at the handle position.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    const overlay = overlayRef.current;
    const map = mapRef.current;
    if (!overlay || !map || !mapReady || !metadata || !comparing || isUncertaintyView) {
      return;
    }
    // Convert swipe fraction → longitude split using current viewport bounds.
    const updateSplit = () => {
      const b = map.getBounds();
      const west = b.getWest();
      const east = b.getEast();
      const splitLon = west + (east - west) * swipeX;

      const { cells: baseCells } = buildCells(false);
      const { cells: scenCells } = buildCells(true);
      const lonOf = (j: number) => metadata.grid.lons[j];

      const layers: Layer[] = [
        new SolidPolygonLayer<CellDatum>({
          id: "field-baseline",
          data: baseCells.filter((d) => lonOf(d.j) <= splitLon),
          getPolygon: (d) => d.polygon,
          getFillColor: (d) => colorFor(d.value),
          pickable: false,
          updateTriggers: { getFillColor: [variable, timeIndex, opacity, cmapParams, swipeX] },
        }),
        new SolidPolygonLayer<CellDatum>({
          id: "field-active",
          data: scenCells.filter((d) => lonOf(d.j) > splitLon),
          getPolygon: (d) => d.polygon,
          getFillColor: (d) => colorFor(d.value),
          pickable: true,
          autoHighlight: true,
          highlightColor: [255, 255, 255, 60],
          onClick: (info) => {
            const obj = info.object as CellDatum | undefined;
            if (obj) setSelectedCell(nearestCell(metadata.grid, lonOf(obj.j), metadata.grid.lats[obj.i]));
          },
          updateTriggers: { getFillColor: [variable, timeIndex, scenario, opacity, cmapParams, swipeX] },
        }),
      ];
      if (selectedCell) {
        layers.push(selectedOutlineLayer(metadata.grid, selectedCell.i, selectedCell.j));
      }
      overlay.setProps({ layers });
    };
    updateSplit();
    map.on("move", updateSplit);
    return () => {
      map.off("move", updateSplit);
    };
  }, [
    comparing,
    swipeX,
    mapReady,
    metadata,
    buildCells,
    colorFor,
    isUncertaintyView,
    selectedCell,
    setSelectedCell,
    variable,
    timeIndex,
    scenario,
    opacity,
    cmapParams,
  ]);

  // swipe handle drag handlers
  const onSwipePointerDown = (e: React.PointerEvent) => {
    swipeDragRef.current = true;
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };
  const onSwipePointerMove = (e: React.PointerEvent) => {
    if (!swipeDragRef.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const f = (e.clientX - rect.left) / rect.width;
    setSwipeX(Math.max(0.04, Math.min(0.96, f)));
  };
  const onSwipePointerUp = () => {
    swipeDragRef.current = false;
  };

  return (
    <div className="maproot">
      <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />

      {usingFallback && (
        <div className="banner">
          offline basemap (external tiles blocked) — graticule fallback active
        </div>
      )}

      {/* hover tooltip */}
      {hover && (
        <div className="tooltip-pop" style={{ left: hover.x, top: hover.y }}>
          <div className="tt-coord">
            {hover.lat.toFixed(2)}°N, {hover.lon.toFixed(2)}°E
          </div>
          <div
            className="tt-val"
            style={{ color: isUncertaintyView ? "var(--accent-warm)" : "var(--accent)" }}
          >
            {hover.value.toFixed(isUncertaintyView || baseVar !== "rainfall" ? 2 : 1)}{" "}
            {isUncertaintyView
              ? "± " + (metadata?.variables[baseVar].units ?? "")
              : metadata?.variables[baseVar].units}
          </div>
        </div>
      )}

      {/* compare swipe handle */}
      {comparing && !isUncertaintyView && (
        <>
          <div
            className="swipe-label"
            style={{ left: `calc(${swipeX * 100}% - 78px)` }}
          >
            ◀ Baseline
          </div>
          <div
            className="swipe-label"
            style={{ left: `calc(${swipeX * 100}% + 12px)` }}
          >
            Scenario ▶
          </div>
          <div
            className="swipe-handle"
            style={{ left: `${swipeX * 100}%` }}
            onPointerDown={onSwipePointerDown}
            onPointerMove={onSwipePointerMove}
            onPointerUp={onSwipePointerUp}
            role="slider"
            aria-label="Compare baseline vs scenario"
            aria-valuenow={Math.round(swipeX * 100)}
          >
            <div className="grip">⇆</div>
          </div>
        </>
      )}
    </div>
  );
}
