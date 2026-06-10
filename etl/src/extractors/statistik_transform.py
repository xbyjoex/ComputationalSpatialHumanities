"""Melt the statistik.leipzig.de wide-by-year formats into long records.

The API serves two CSV layouts (and a long JSON variant):

- /api/values (stadtweit):  Kennziffer, Merkmal_1..4, Einheit, 2001, 2002, ...
  one row per indicator, one column per year
- /api/kdvalues (kleinräumig): Gebiet, Sachmerkmal, 2000, 2001, ...
  one row per Ortsteil × indicator

The generic loader used to treat the year columns as metrics named "2001",
which also made different indicator rows collide on the statistics upsert
key (same dataset/period/spatial/metric) and silently overwrite each other.
This module melts both layouts into records the generic loader handles
correctly: one record per (year[, Gebiet]) with one key per indicator.
"""

from __future__ import annotations

import re
from typing import Any

# Period columns: "2003", "1.Qu. 2003", "2001/02" (Schuljahr), "Jan. 2024" —
# anything carrying a year that is not one of the meta columns.
_HAS_YEAR = re.compile(r"(19|20)\d{2}")
_META_COLS = {
    "Kennziffer", "Merkmal_1", "Merkmal_2", "Merkmal_3", "Merkmal_4",
    "Einheit", "Gebiet", "Sachmerkmal",
}


def _is_period_col(col: str) -> bool:
    return col not in _META_COLS and bool(_HAS_YEAR.search(col))


def is_statistik_url(url: str) -> bool:
    return "statistik.leipzig.de/opendata/api" in url


def _metric_name(row: dict[str, Any]) -> str:
    """Stable indicator name from the Merkmal hierarchy.

    Kennziffer alone is ambiguous ("Männer" appears in many datasets);
    Merkmal_2..4 carry the actual hierarchy (e.g. Beschäftigte · Männer).
    """
    parts = [
        str(row.get(k) or "").strip()
        for k in ("Merkmal_2", "Merkmal_3", "Merkmal_4")
    ]
    name = " · ".join(p for p in parts if p)
    return name or str(row.get("Kennziffer") or "").strip()


def melt_values(
    rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Stadtweite values: → one record per year, one key per indicator."""
    by_year: dict[str, dict[str, Any]] = {}
    units: dict[str, str] = {}
    for row in rows:
        name = _metric_name(row)
        if not name:
            continue
        unit = str(row.get("Einheit") or "").strip()
        if unit:
            units[name] = unit
        for col, val in row.items():
            if not _is_period_col(str(col)) or val in (None, ""):
                continue
            record = by_year.setdefault(str(col), {"Jahr": str(col)})
            record[name] = val
    return [by_year[y] for y in sorted(by_year)], units


def melt_kdvalues(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kleinräumige kdvalues: → one record per (Gebiet, year)."""
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        gebiet = str(row.get("Gebiet") or "").strip()
        merkmal = str(row.get("Sachmerkmal") or "").strip()
        if not gebiet or not merkmal:
            continue
        for col, val in row.items():
            if not _is_period_col(str(col)) or val in (None, ""):
                continue
            record = by_key.setdefault(
                (gebiet, str(col)), {"Jahr": str(col), "Ortsteil": gebiet}
            )
            record[merkmal] = val
    return [by_key[k] for k in sorted(by_key)]


def melt_json_values(
    rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """JSON variant: already long (name/merkmal_*/wert/jahr/einheit per row)."""
    by_period: dict[str, dict[str, Any]] = {}
    units: dict[str, str] = {}
    for row in rows:
        parts = [
            str(row.get(k) or "").strip()
            for k in ("merkmal_2", "merkmal_3", "merkmal_4")
        ]
        name = " · ".join(p for p in parts if p) or str(row.get("name") or "").strip()
        period = str(row.get("jahr") or "").strip()
        if not name or not period:
            continue
        unit = str(row.get("einheit") or "").strip()
        if unit:
            units[name] = unit
        value = row.get("wert")
        if value in (None, "", "x"):
            continue
        record = by_period.setdefault(period, {"Jahr": period})
        record[name] = value
    return [by_period[p] for p in sorted(by_period)], units
