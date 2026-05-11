"""Extract tabular data from XLSX / ODS files."""

from __future__ import annotations

import io
import logging
from typing import Any

import pandas as pd

from .base import HttpExtractor

logger = logging.getLogger(__name__)


class ExcelExtractor(HttpExtractor):
    def extract(self, url: str, fmt: str = "XLSX") -> list[dict[str, Any]]:
        raw = self.get_bytes(url)
        engine = "odf" if fmt.upper() == "ODS" else "openpyxl"

        try:
            df = pd.read_excel(io.BytesIO(raw), sheet_name=0, engine=engine, dtype=str)
        except Exception:
            # Fall back to first non-empty sheet
            sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, engine=engine, dtype=str)
            df = next((v for v in sheets.values() if not v.empty), pd.DataFrame())

        df = df.dropna(how="all").fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        records = df.to_dict(orient="records")
        logger.info("Excel/%s: %d rows from %s", fmt, len(records), url)
        return records
