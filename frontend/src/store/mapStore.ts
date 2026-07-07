import { create } from "zustand";

export type LayerKey = "geo_features" | "park_ride" | "bicycle" | "restrictions" | "choropleth" | "elections";

/** A non-geo statistic pinned to the bottom context dock (chart, not map). */
export interface DockItem {
  datasetId: string;
  title: string;
  kind: "timeseries" | "distribution";
}

/** Aktive Wahl-Auswahl für die Politisches-Spektrum-Ebene. */
export interface ElectionSelection {
  electionType: string;
  year: number;
  level: string;
}

interface MapState {
  activeLayers: Set<LayerKey>;
  selectedDatasetIds: string[];
  selectedFamilyIds: string[];
  choroplethMetric: string;
  /** Dataset whose metric the active choropleth is drawn from (scopes the picker). */
  choroplethDatasetId: string | null;
  correlationMetricA: string;
  correlationMetricB: string;
  /** Globales Jahr — filtert Datenebene (Tile-Styles) UND Choroplethen. */
  timelineYear: number | null;
  spatialUnit: string;
  electionSelection: ElectionSelection | null;
  sidebarTab: "layers" | "stats" | "datasets";
  /** Non-geo statistics shown as charts in the bottom dock. */
  dockItems: DockItem[];
  toggleLayer: (key: LayerKey) => void;
  setLayer: (key: LayerKey, on: boolean) => void;
  setSelectedDatasets: (ids: string[]) => void;
  toggleDatasetId: (id: string) => void;
  toggleFamilyId: (id: string) => void;
  setChoropleth: (datasetId: string | null, metric: string) => void;
  setChoroplethMetric: (m: string) => void;
  setCorrelationMetrics: (a: string, b: string) => void;
  setTimelineYear: (y: number | null) => void;
  setSpatialUnit: (u: string) => void;
  setElectionSelection: (sel: ElectionSelection | null) => void;
  setSidebarTab: (t: MapState["sidebarTab"]) => void;
  toggleDockItem: (item: DockItem) => void;
  removeDockItem: (datasetId: string) => void;
}

export const useMapStore = create<MapState>((set) => ({
  activeLayers: new Set(["restrictions"]),
  selectedDatasetIds: [],
  selectedFamilyIds: [],
  choroplethMetric: "",
  choroplethDatasetId: null,
  correlationMetricA: "",
  correlationMetricB: "",
  timelineYear: null,
  spatialUnit: "ortsteil",
  electionSelection: null,
  sidebarTab: "layers",
  dockItems: [],

  toggleLayer: (key) =>
    set((s) => {
      const next = new Set(s.activeLayers);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return { activeLayers: next };
    }),

  setLayer: (key, on) =>
    set((s) => {
      const next = new Set(s.activeLayers);
      if (on) next.add(key);
      else next.delete(key);
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
  setChoropleth: (datasetId, metric) =>
    set({ choroplethDatasetId: datasetId, choroplethMetric: metric }),
  setChoroplethMetric: (m) => set({ choroplethMetric: m }),
  setCorrelationMetrics: (a, b) => set({ correlationMetricA: a, correlationMetricB: b }),
  setTimelineYear: (y) => set({ timelineYear: y }),
  setSpatialUnit: (u) => set({ spatialUnit: u }),
  setElectionSelection: (sel) => set({ electionSelection: sel }),
  setSidebarTab: (t) => set({ sidebarTab: t }),
  toggleDockItem: (item) =>
    set((s) => ({
      dockItems: s.dockItems.some((d) => d.datasetId === item.datasetId)
        ? s.dockItems.filter((d) => d.datasetId !== item.datasetId)
        : [...s.dockItems, item],
    })),
  removeDockItem: (datasetId) =>
    set((s) => ({ dockItems: s.dockItems.filter((d) => d.datasetId !== datasetId) })),
}));
