import { apiClient } from "./client";

export interface FeatureGroup {
  group_id: string;
  title: string;
  is_family: boolean;
  dataset_ids: string[];
  years: number[];
  feature_count: number;
  geometry_types: string[];
}

export const fetchFeatureGroups = (): Promise<FeatureGroup[]> =>
  apiClient.get("/map/feature-datasets").then((r) => r.data);

// Tile-URL mit literalen {z}/{x}/{y}-Platzhaltern. Läuft über das eigene
// leipzig://-Protokoll (src/map/tileProtocol.ts): JWT-Header + Ladefortschritt.
export const buildTileUrl = (datasetIds: string[], familyIds: string[]): string => {
  const p = new URLSearchParams();
  [...datasetIds].sort().forEach((id) => p.append("dataset_ids", id));
  [...familyIds].sort().forEach((id) => p.append("family_ids", id));
  return `leipzig://api/map/tiles/{z}/{x}/{y}.pbf?${p.toString()}`;
};

export interface FeatureDetail {
  id: number;
  dataset_id: string;
  dataset_title: string;
  family_id: string | null;
  feature_type: string | null;
  name: string | null;
  description: string | null;
  year: number | null;
  properties: Record<string, unknown> | null;
  valid_from: string | null;
  valid_until: string | null;
  updated_at: string | null;
}

export const fetchFeatureDetail = (id: number): Promise<FeatureDetail> =>
  apiClient.get(`/map/feature/${id}`).then((r) => r.data);

export const fetchParkRide = () =>
  apiClient.get("/map/park-ride").then((r) => r.data);

export const fetchBicycleCounters = (days = 7) =>
  apiClient.get("/map/bicycle-counters", { params: { days } }).then((r) => r.data);

export const fetchRestrictions = () =>
  apiClient.get("/map/restrictions").then((r) => r.data);

export const fetchAdminBoundaries = (boundary_type = "ortsteil") =>
  apiClient.get("/map/admin-boundaries", { params: { boundary_type } }).then((r) => r.data);

export const fetchChoropleth = (metric_name: string, spatial_unit = "ortsteil", period_year?: number) =>
  apiClient.get("/stats/choropleth", { params: { metric_name, spatial_unit, period_year } }).then((r) => r.data);

export const fetchCorrelation = (metric_a: string, metric_b: string, spatial_unit = "ortsteil", period_year?: number) =>
  apiClient.get("/stats/correlation", { params: { metric_a, metric_b, spatial_unit, period_year } }).then((r) => r.data);

// Nur Metriken, die für die Raumeinheit auch kartierbar sind (numerisch +
// aufgelöster Boundary-Code) — sonst flutet jede CSV-Spalte das Dropdown.
export const fetchMetrics = (spatial_unit?: string, dataset_id?: string) =>
  apiClient.get("/stats/metrics", { params: { spatial_unit, dataset_id } }).then((r) => r.data);

export const fetchDatasets = (params?: Record<string, unknown>) =>
  apiClient.get("/datasets", { params }).then((r) => r.data);

export const fetchDatasetStatus = () =>
  apiClient.get("/datasets/status").then((r) => r.data);
