import { apiClient } from "./client";

export interface DatasetRow {
  id: string;
  name?: string;
  title: string;
  schedule: "nightly" | "live";
  has_geo: boolean;
  formats: string[] | null;
  best_format: string | null;
  best_url: string | null;
  last_ingested: string | null;
  is_active: boolean;
  family_id?: string | null;
  family_year?: number | null;
  categories?: string[];
}

export interface Category {
  category_id: string;
  title: string;
  description: string | null;
  position: number;
  dataset_count: number;
  geo_count: number;
  family_count: number;
}

export interface CategoryDatasetEntry {
  id: string;
  name: string;
  title: string;
  schedule: "nightly" | "live";
  has_geo: boolean;
  best_format: string | null;
  family_id: string | null;
  family_year: number | null;
  family_title: string | null;
  last_ingested: string | null;
  last_run_status: string | null;
  last_run_at: string | null;
  last_run_rows: number | null;
}

export interface CategoryDatasetsResponse {
  category: { category_id: string; title: string; description: string | null };
  families: Array<{
    family_id: string;
    title: string | null;
    members: CategoryDatasetEntry[];
  }>;
  datasets: CategoryDatasetEntry[];
}

export interface DatasetListResponse {
  total: number;
  limit: number;
  offset: number;
  items: DatasetRow[];
}

export interface DatasetDetail {
  dataset: DatasetRow & { metadata?: Record<string, unknown> };
  categories?: Array<{ category_id: string; title: string }>;
  target_table: string | null;
  row_count: number;
  recent_runs: Array<{
    status: string;
    started_at: string;
    finished_at: string | null;
    rows_loaded: number | null;
    rows_extracted: number | null;
    duration_ms: number | null;
    error_message: string | null;
  }>;
}

export interface DatasetRowsResponse {
  target_table: string | null;
  total: number;
  limit: number;
  offset: number;
  columns: string[];
  items: Record<string, unknown>[];
}

export interface DatasetStatsResponse {
  target_table: string | null;
  summary?: Record<string, unknown>;
  per_metric?: Array<Record<string, unknown>>;
  per_type?: Array<Record<string, unknown>>;
  per_site?: Array<Record<string, unknown>>;
  per_counter?: Array<Record<string, unknown>>;
}

export interface DatasetHistoryEntry {
  id: number;
  run_id: number | null;
  target_table: string;
  rows_added: number;
  rows_updated: number;
  rows_total_after: number | null;
  created_at: string;
  status: string | null;
  duration_ms: number | null;
  error_message: string | null;
}

export interface DatasetHistoryResponse {
  history: DatasetHistoryEntry[];
  runs: Array<{
    id: number;
    status: string;
    started_at: string;
    finished_at: string | null;
    rows_loaded: number | null;
    rows_extracted: number | null;
    duration_ms: number | null;
    error_message: string | null;
  }>;
}

export const listDatasets = (params: {
  search?: string;
  schedule?: string;
  has_geo?: boolean;
  format?: string;
  category?: string;
  limit?: number;
  offset?: number;
}) =>
  apiClient
    .get<DatasetListResponse>("/datasets", { params })
    .then((r) => r.data);

export const listCategories = () =>
  apiClient.get<Category[]>("/datasets/categories").then((r) => r.data);

export const getCategoryDatasets = (categoryId: string) =>
  apiClient
    .get<CategoryDatasetsResponse>(`/datasets/categories/${encodeURIComponent(categoryId)}`)
    .then((r) => r.data);

export const getDatasetBySlug = (slug: string) =>
  apiClient
    .get<DatasetDetail>(`/datasets/by-slug/${encodeURIComponent(slug)}`)
    .then((r) => r.data);

export const getDataset = (id: string) =>
  apiClient.get<DatasetDetail>(`/datasets/${encodeURIComponent(id)}`).then((r) => r.data);

export const getDatasetRows = (
  id: string,
  params: { search?: string; limit?: number; offset?: number }
) =>
  apiClient
    .get<DatasetRowsResponse>(`/datasets/${encodeURIComponent(id)}/rows`, { params })
    .then((r) => r.data);

export const getDatasetStats = (id: string) =>
  apiClient
    .get<DatasetStatsResponse>(`/datasets/${encodeURIComponent(id)}/stats`)
    .then((r) => r.data);

export interface ProfileColumn {
  name: string;
  kind: "numeric" | "categorical" | "date";
  n?: number;
  non_null?: number;
  null_share?: number | null;
  min?: number | string | null;
  max?: number | string | null;
  mean?: number | null;
  median?: number | null;
  stddev?: number | null;
  year_min?: number | null;
  year_max?: number | null;
  distinct?: number;
  top?: Array<{ value: string; n: number }>;
  histogram_column?: string;
}

export interface DatasetProfile {
  target_table: string | null;
  row_count: number;
  columns: ProfileColumn[];
}

export interface Histogram {
  column: string;
  lo: number | null;
  hi: number | null;
  buckets: Array<{ lo: number; hi: number; n: number }>;
}

export const getDatasetProfile = (id: string) =>
  apiClient
    .get<DatasetProfile>(`/datasets/${encodeURIComponent(id)}/profile`)
    .then((r) => r.data);

export const getDatasetHistogram = (id: string, column: string) =>
  apiClient
    .get<Histogram>(`/datasets/${encodeURIComponent(id)}/profile/histogram`, {
      params: { column },
    })
    .then((r) => r.data);

export const getDatasetHistory = (id: string, limit = 100) =>
  apiClient
    .get<DatasetHistoryResponse>(`/datasets/${encodeURIComponent(id)}/history`, {
      params: { limit },
    })
    .then((r) => r.data);
