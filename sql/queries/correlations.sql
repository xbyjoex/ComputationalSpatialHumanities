-- Correlation query: compare two metrics across shared spatial units
-- Parameters: :metric_a :metric_b :spatial_unit :period_year
SELECT
    a.spatial_key,
    a.metric_value AS value_a,
    b.metric_value AS value_b,
    CORR(a.metric_value, b.metric_value) OVER () AS pearson_r
FROM mart.statistics_latest a
JOIN mart.statistics_latest b
    ON  a.spatial_unit = b.spatial_unit
    AND a.spatial_key  = b.spatial_key
    AND (:period_year IS NULL OR a.period_year = :period_year)
    AND (:period_year IS NULL OR b.period_year = :period_year)
WHERE a.metric_name  = :metric_a
  AND b.metric_name  = :metric_b
  AND a.spatial_unit = :spatial_unit
ORDER BY a.spatial_key;
