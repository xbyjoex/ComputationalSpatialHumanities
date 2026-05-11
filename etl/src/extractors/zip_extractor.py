"""Extract data from ZIP archives — detects content and delegates."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import tempfile
import zipfile
from typing import Any

from .base import HttpExtractor

logger = logging.getLogger(__name__)

MAX_FEATURES = 100_000


class ZipExtractor(HttpExtractor):
    def extract(self, url: str) -> tuple[str, list[dict[str, Any]]]:
        """
        Download a ZIP and detect its content.
        Returns (detected_format, features_or_records).
        Caller is responsible for routing to the right loader.
        """
        raw = self.get_bytes(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                zf.extractall(tmpdir)

            for root, _, files in os.walk(tmpdir):
                for fname in sorted(files):
                    fpath = os.path.join(root, fname)
                    lower = fname.lower()

                    if lower.endswith(".geojson") or lower.endswith(".json"):
                        logger.info("ZIP contains GeoJSON: %s", fname)
                        return "GeoJSON", self._load_geojson(fpath)

                    if lower.endswith(".shp"):
                        logger.info("ZIP contains SHP: %s", fname)
                        # Let ShapefileExtractor handle via its own URL flow;
                        # here we return the path hint so pipeline can re-route.
                        # Realistically won't be hit — SHP format uses ShapefileExtractor.
                        return "SHP", []

                    if lower.endswith(".csv"):
                        logger.info("ZIP contains CSV: %s", fname)
                        return "CSV", self._load_csv(fpath)

        logger.warning("ZIP from %s: no recognised content", url)
        return "unknown", []

    def _load_geojson(self, path: str) -> list[dict[str, Any]]:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            features = data.get("features", [])
        elif isinstance(data, list):
            features = data
        else:
            features = []
        if len(features) > MAX_FEATURES:
            logger.warning("ZIP GeoJSON truncated at %d features", MAX_FEATURES)
            features = features[:MAX_FEATURES]
        return features

    def _load_csv(self, path: str) -> list[dict[str, Any]]:
        rows = []
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({k.strip(): (v.strip() if v else None)
                              for k, v in row.items() if k is not None})
                if len(rows) >= MAX_FEATURES:
                    break
        return rows
