"""Extract GeoJSON / WFS features from a URL."""

from __future__ import annotations

import logging
from typing import Any, Generator

from .base import HttpExtractor

logger = logging.getLogger(__name__)


class GeoJsonExtractor(HttpExtractor):
    def extract(self, url: str) -> Generator[dict[str, Any], None, None]:
        """Yield individual GeoJSON feature dicts from a FeatureCollection URL."""
        data = self.get_json(url)

        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            features = data.get("features", [])
            logger.info("GeoJSON: %d features from %s", len(features), url)
            yield from features
        elif isinstance(data, list):
            # Some endpoints return a bare array of feature objects
            yield from data
        else:
            logger.warning("Unexpected GeoJSON structure from %s: %s", url, type(data))

    def extract_all(self, url: str) -> list[dict[str, Any]]:
        return list(self.extract(url))
