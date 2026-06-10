"""Extract tabular data from CSV / XLSX URLs."""

from __future__ import annotations

import csv
import io
import logging
from typing import Any, Generator

from .base import HttpExtractor

logger = logging.getLogger(__name__)


def _sniff_delimiter(text: str, default: str = ",") -> str:
    """Detect the delimiter from the header line — German open-data CSVs
    are predominantly semicolon-separated."""
    header = text.split("\n", 1)[0]
    counts = {d: header.count(d) for d in (";", ",", "\t", "|")}
    best = max(counts, key=counts.get)  # type: ignore[arg-type]
    return best if counts[best] > 0 else default


class CsvExtractor(HttpExtractor):
    def extract(
        self, url: str, delimiter: str | None = None, encoding: str = "utf-8-sig"
    ) -> Generator[dict[str, Any], None, None]:
        raw = self.get_bytes(url)
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        text = text.replace("\x00", "")

        if delimiter is None:
            delimiter = _sniff_delimiter(text)

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
