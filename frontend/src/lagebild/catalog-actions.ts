/**
 * Shared selection logic for the Lagebild catalog — used both when the user
 * clicks an entry and when a preset selects several at once. Keeping it in one
 * place means a preset and a manual click drive the exact same state.
 */
import type { CatalogEntry } from "../api/catalog";
import type { useMapStore } from "../store/mapStore";

type Store = ReturnType<typeof useMapStore.getState>;

/** Geo feature_types that warrant their own live-styled treatment. */
export const LIVE_GEO_TYPES = new Set([
  "park_ride",
  "park_ride_history",
  "bicycle_count",
  "bicycle_station",
  "gtfs_stop",
]);

export function isEntryActive(e: CatalogEntry, s: Store): boolean {
  if (e.traffic) return s.activeLayers.has("restrictions");
  switch (e.kind) {
    case "geo":
      return e.is_family
        ? s.selectedFamilyIds.includes(e.group_id)
        : s.selectedDatasetIds.includes(e.group_id);
    case "choropleth":
      return s.choroplethDatasetId === e.dataset_ids[0];
    default:
      return s.dockItems.some((d) => d.datasetId === e.dataset_ids[0]);
  }
}

/** Toggle (or force, via `on`) an entry's presence on the Lagebild. */
export function applyEntry(e: CatalogEntry, s: Store, on?: boolean): void {
  const active = isEntryActive(e, s);
  const turnOn = on ?? !active;

  // Traffic restrictions have their own live GeoJSON layer.
  if (e.traffic) {
    s.setLayer("restrictions", turnOn);
    return;
  }

  if (e.kind === "geo") {
    if (turnOn) s.setLayer("geo_features", true);
    if (e.is_family) {
      if (s.selectedFamilyIds.includes(e.group_id) !== turnOn) s.toggleFamilyId(e.group_id);
    } else if (s.selectedDatasetIds.includes(e.group_id) !== turnOn) {
      s.toggleDatasetId(e.group_id);
    }
    return;
  }

  if (e.kind === "choropleth") {
    if (turnOn) {
      // Metric is chosen by the ChoroplethControl (defaults to the first one).
      s.setChoropleth(e.dataset_ids[0], "");
      s.setLayer("choropleth", true);
    } else if (s.choroplethDatasetId === e.dataset_ids[0]) {
      s.setChoropleth(null, "");
      s.setLayer("choropleth", false);
    }
    return;
  }

  // timeseries / distribution → bottom context dock
  const present = s.dockItems.some((d) => d.datasetId === e.dataset_ids[0]);
  if (present !== turnOn) {
    s.toggleDockItem({
      datasetId: e.dataset_ids[0],
      title: e.title,
      kind: e.kind === "distribution" ? "distribution" : "timeseries",
    });
  }
}

export interface Preset {
  id: string;
  label: string;
  /** Selects the matching catalog entries; live layers toggled separately. */
  match: (e: CatalogEntry) => boolean;
  /** Extra layer keys to enable (e.g. live restrictions). */
  layers?: ("restrictions" | "geo_features" | "choropleth")[];
}

const titleHas = (e: CatalogEntry, ...needles: string[]) =>
  needles.some((n) => e.title.toLowerCase().includes(n));

export const PRESETS: Preset[] = [
  {
    id: "mobilitaet",
    label: "Mobilität",
    layers: ["restrictions"],
    match: (e) =>
      e.feature_types.some((t) => LIVE_GEO_TYPES.has(t)) ||
      titleHas(e, "straßennetz", "radverkehr", "park+ride", "park + ride"),
  },
  {
    id: "stadtklima",
    label: "Stadtklima",
    match: (e) =>
      titleHas(e, "baumkataster", "luftqualität", "luftreinhalte", "no2", "bodenrichtwerte"),
  },
  {
    id: "wahlen",
    label: "Wahlen",
    match: (e) => titleHas(e, "wahlbezirke", "wahlkreise") && e.kind === "geo",
  },
  {
    id: "bevoelkerung",
    label: "Bevölkerung",
    match: (e) =>
      e.theme === "bevoelkerung-und-gesellschaft" &&
      (e.kind === "choropleth" || e.kind === "timeseries"),
  },
];
