"""Extract tabular data from CSV / XLSX URLs."""

from __future__ import annotations

import csv
import io
import logging
from typing import Any, Generator

from .base import HttpExtractor

logger = logging.getLogger(__name__)


class CsvExtractor(HttpExtractor):
    def extract(
        self, url: str, delimiter: str = ",", encoding: str = "utf-8-sig"
    ) -> Generator[dict[str, Any], None, None]:
        raw = self.get_bytes(url)
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        text = text.replace("\x00", "")

        # newline='' required for CSVs with embedded newlines in quoted fields
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
        for row in reader:
            yield {k.strip(): (v.strip() if v else None) for k, v in row.items() if k is not None}

    def extract_all(self, url: str, max_rows: int = 50_000, **kwargs: Any) -> list[dict[str, Any]]:
        rows = []
        for row in self.extract(url, **kwargs):
            rows.append(row)
            if len(rows) >= max_rows:
                logger.warning("CSV truncated at %d rows (url=%s)", max_rows, url)
                break
        return rows
