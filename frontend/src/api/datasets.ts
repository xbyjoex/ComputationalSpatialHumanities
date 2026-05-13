import { apiClient } from "./client";

export interface DatasetRow {
  id: string;
  title: string;
  schedule: "nightly" | "live";
  has_geo: boolean;
  formats: string[] | null;
  best_format: string | null;
  best_url: string | null;
  last_ingested: string | null;
  is_active: boolean;
}

export interface DatasetListResponse {
  total: number;
  limit: number;
  offset: number;
  items: DatasetRow[];
}

export interface DatasetDetail {
  dataset: DatasetRow & { metadata?: Record<string, unknown> };
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
  limit?: number;
  offset?: number;
}) =>
  apiClient
    .get<DatasetListResponse>("/datasets", { params })
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

export const getDatasetHistory = (id: string, limit = 100) =>
  apiClient
    .get<DatasetHistoryResponse>(`/datasets/${encodeURIComponent(id)}/history`, {
      params: { limit },
    })
    .then((r) => r.data);
