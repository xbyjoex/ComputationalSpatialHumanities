import { apiClient } from "./client";

export interface BboxParams {
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
  dataset_ids?: string[];
  feature_types?: string[];
}

export const fetchMapFeatures = (params: BboxParams) =>
  apiClient.get("/map/features", { params }).then((r) => r.data);

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

export const fetchMetrics = (dataset_id?: string) =>
  apiClient.get("/stats/metrics", { params: { dataset_id } }).then((r) => r.data);

export const fetchDatasets = (params?: Record<string, unknown>) =>
  apiClient.get("/datasets", { params }).then((r) => r.data);

export const fetchDatasetStatus = () =>
  apiClient.get("/datasets/status").then((r) => r.data);
