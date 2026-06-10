import { apiClient } from "./client";

/** How a dataset is primarily represented on the Lagebild. */
export type CatalogKind = "geo" | "choropleth" | "timeseries" | "distribution";

export interface CatalogEntry {
  group_id: string;
  is_family: boolean;
  title: string;
  slug: string;
  /** Primary thematic category id (matches /datasets/categories). */
  theme: string;
  dataset_ids: string[];
  kind: CatalogKind;
  /** ["Live","Geo","Ortsteil","Stadt","Zeitreihe"] */
  badges: string[];
  /** "point" | "line" | "area" | null */
  geometry: string | null;
  feature_types: string[];
  years: number[];
  feature_count: number | null;
  ort_metrics: number;
  city_metrics: number;
  live: boolean;
  /** Traffic restrictions render via the dedicated live layer, not geo tiles. */
  traffic: boolean;
}

export const fetchCatalog = (): Promise<CatalogEntry[]> =>
  apiClient.get("/datasets/catalog").then((r) => r.data);
