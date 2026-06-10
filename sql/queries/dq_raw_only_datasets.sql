-- Data-quality review: datasets whose ETL extracted rows but never wrote
-- anything to a core table (generic raw-only fallback). Run manually:
--   psql -U leipzig -d leipzig_data < sql/queries/dq_raw_only_datasets.sql

-- Datasets with a raw payload summary but no change_log entry (no core rows ever)
SELECT p.dataset_id,
       d.title,
       d.best_format,
       p.payload,
       p.ingested_at
FROM raw_ingest.payloads p
LEFT JOIN core.datasets d ON d.id = p.dataset_id
WHERE NOT EXISTS (
    SELECT 1 FROM raw_ingest.change_log c WHERE c.dataset_id = p.dataset_id
)
ORDER BY d.title;

-- Recent runs flagged by the DQ guard in etl/src/pipeline.py
SELECT dataset_id, dataset_title, rows_extracted, started_at
FROM raw_ingest.etl_runs
WHERE status = 'success'
  AND error_message = 'DQ: raw-only ingest (no core rows)'
  AND started_at > NOW() - INTERVAL '7 days'
ORDER BY started_at DESC;
