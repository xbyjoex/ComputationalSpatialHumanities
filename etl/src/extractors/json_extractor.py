"""Extract JSON statistical data from statistik.leipzig.de API."""

from __future__ import annotations

import logging
from typing import Any

from .base import HttpExtractor

logger = logging.getLogger(__name__)


class StatistikApiExtractor(HttpExtractor):
    """
    Handles statistik.leipzig.de opendata API endpoints.

    Endpoint patterns:
      /api/values?kategorie_nr=X&rubrik_nr=Y&perioden=N&...
      /api/kdvalues?kategorie_nr=X&rubrik_nr=Y&...  (Kleinräumige Daten)
    """

    def extract_values(self, url: str) -> list[dict[str, Any]]:
        data = self.get_json(url)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "values" in data:
            return data["values"]
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        logger.warning("Unexpected statistics API response from %s", url)
        return [data] if data else []

    def extract_kdvalues(self, url: str) -> list[dict[str, Any]]:
        """Kleinräumige Daten — returns records with Ortsteil/Stadtbezirk breakdown."""
        return self.extract_values(url)
