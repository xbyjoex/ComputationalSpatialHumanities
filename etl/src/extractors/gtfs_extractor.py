"""Extract GTFS feed — stops as geo features, agencies/routes as raw records."""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from typing import Any

from .base import HttpExtractor

logger = logging.getLogger(__name__)


class GtfsExtractor(HttpExtractor):
    def extract_stops(self, url: str) -> list[dict[str, Any]]:
        """Return stops as GeoJSON feature dicts (Point geometries)."""
        raw = self.get_bytes(url)
        features: list[dict[str, Any]] = []

        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            stops_name = next((n for n in names if n.endswith("stops.txt")), None)
            if not stops_name:
                logger.warning("No stops.txt in GTFS feed from %s", url)
                return []

            with zf.open(stops_name) as raw_f:
                reader = csv.DictReader(io.TextIOWrapper(raw_f, encoding="utf-8-sig"))
                for row in reader:
                    try:
                        lat = float(row.get("stop_lat") or 0)
                        lon = float(row.get("stop_lon") or 0)
                    except ValueError:
                        continue
                    if not lat or not lon:
                        continue
                    props = {k: v for k, v in row.items()
                             if k not in ("stop_lat", "stop_lon")}
                    # Normalise common property names for upsert_geo_features
                    props.setdefault("id", props.get("stop_id", ""))
                    props.setdefault("name", props.get("stop_name", ""))
                    features.append({
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lon, lat]},
                        "properties": props,
                    })

        logger.info("GTFS: %d stops from %s", len(features), url)
        return features

    def extract_routes(self, url: str) -> list[dict[str, Any]]:
        """Return routes as plain record dicts for statistics storage."""
        raw = self.get_bytes(url)
        records: list[dict[str, Any]] = []

        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            routes_name = next((n for n in names if n.endswith("routes.txt")), None)
            if not routes_name:
                return []

            with zf.open(routes_name) as raw_f:
                reader = csv.DictReader(io.TextIOWrapper(raw_f, encoding="utf-8-sig"))
                records = list(reader)

        logger.info("GTFS: %d routes from %s", len(records), url)
        return records
