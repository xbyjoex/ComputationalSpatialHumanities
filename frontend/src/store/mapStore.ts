import { create } from "zustand";

export type LayerKey = "geo_features" | "park_ride" | "bicycle" | "restrictions" | "choropleth";

interface MapState {
  activeLayers: Set<LayerKey>;
  selectedDatasetIds: string[];
  selectedFamilyIds: string[];
  choroplethMetric: string;
  correlationMetricA: string;
  correlationMetricB: string;
  /** Globales Jahr — filtert Datenebene (Tile-Styles) UND Choroplethen. */
  timelineYear: number | null;
  spatialUnit: string;
  sidebarTab: "layers" | "stats" | "datasets";
  toggleLayer: (key: LayerKey) => void;
  setSelectedDatasets: (ids: string[]) => void;
  toggleDatasetId: (id: string) => void;
  toggleFamilyId: (id: string) => void;
  setChoroplethMetric: (m: string) => void;
  setCorrelationMetrics: (a: string, b: string) => void;
  setTimelineYear: (y: number | null) => void;
  setSpatialUnit: (u: string) => void;
  setSidebarTab: (t: MapState["sidebarTab"]) => void;
}

export const useMapStore = create<MapState>((set) => ({
  activeLayers: new Set(["park_ride", "restrictions"]),
  selectedDatasetIds: [],
  selectedFamilyIds: [],
  choroplethMetric: "",
  correlationMetricA: "",
  correlationMetricB: "",
  timelineYear: null,
  spatialUnit: "ortsteil",
  sidebarTab: "layers",

  toggleLayer: (key) =>
    set((s) => {
      const next = new Set(s.activeLayers);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return { activeLayers: next };
    }),

  setSelectedDatasets: (ids) => set({ selectedDatasetIds: ids }),
  toggleDatasetId: (id) =>
    set((s) => ({
      selectedDatasetIds: s.selectedDatasetIds.includes(id)
        ? s.selectedDatasetIds.filter((x) => x !== id)
        : [...s.selectedDatasetIds, id],
    })),
  toggleFamilyId: (id) =>
    set((s) => ({
      selectedFamilyIds: s.selectedFamilyIds.includes(id)
        ? s.selectedFamilyIds.filter((x) => x !== id)
        : [...s.selectedFamilyIds, id],
    })),
  setChoroplethMetric: (m) => set({ choroplethMetric: m }),
  setCorrelationMetrics: (a, b) => set({ correlationMetricA: a, correlationMetricB: b }),
  setTimelineYear: (y) => set({ timelineYear: y }),
  setSpatialUnit: (u) => set({ spatialUnit: u }),
  setSidebarTab: (t) => set({ sidebarTab: t }),
}));
