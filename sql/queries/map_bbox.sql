-- Bounding-box filtered geo features for map tile requests
-- Parameters: :xmin :ymin :xmax :ymax :dataset_ids (array) :feature_types (array)
SELECT
    id,
    dataset_id,
    dataset_title,
    feature_type,
    name,
    ST_AsGeoJSON(geom)::jsonb AS geometry,
    properties,
    valid_from,
    valid_until
FROM mart.geo_features_map
WHERE geom && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 4326)
  AND (:dataset_ids IS NULL OR dataset_id = ANY(:dataset_ids))
  AND (:feature_types IS NULL OR feature_type = ANY(:feature_types))
LIMIT 2000;
