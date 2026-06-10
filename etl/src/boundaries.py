"""Seed core.admin_boundaries from the official boundary datasets.

The boundary geometries are the join targets that put Ortsteil-/Stadtbezirk-/
Wahlbezirk-keyed statistics on the map. Sources (verified against live
payloads):

- Ortsteile:     GeoJSON, EPSG:25833, props {FID, OT: "00", Name: "Zentrum"}
- Stadtbezirke:  GeoJSON, EPSG:25833, props {FID, SBZ: "0", Name: "Mitte"}
- Wahlbezirke:   SHP (ETRS89 UTM33N via .prj), field wbz = "0338" (4-digit,
                 zero-padded); no name field. Geometries differ per election,
                 hence boundary_year 2021 / 2025.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import psycopg

from .db import get_conn
from .extractors.base import HttpExtractor
from .extractors.shapefile_extractor import ShapefileExtractor, _reproject_feature

logger = logging.getLogger(__name__)

# Minimum share of features that must yield a code — below this the source
# layout has changed and silent partial seeding would corrupt joins.
_MIN_CODE_RATIO = 0.9

BOUNDARY_SOURCES: list[dict[str, Any]] = [
    {
        "dataset_id": "74b342a9-7db7-45a3-8404-944442a24d51",
        "boundary_type": "ortsteil",
        "boundary_year": 0,
        "code_keys": ("OT", "ot", "Nummer", "nummer", "nr", "code"),
        "name_keys": ("Name", "name", "OT_Name", "bezeichnung"),
        # Leipzig Ortsteil codes are two digits; the first digit is the
        # Stadtbezirk ("04" Plagwitz → Stadtbezirk "0" ... official scheme).
        "parent_from_first_digit": True,
    },
    {
        "dataset_id": "eebf6dcb-6806-4c3f-8f25-d2763cae3da6",
        "boundary_type": "stadtbezirk",
        "boundary_year": 0,
        "code_keys": ("SBZ", "sbz", "Nummer", "nummer", "nr", "code"),
        "name_keys": ("Name", "name", "bezeichnung"),
    },
    {
        "dataset_id": "3e23daff-60cc-449c-9c12-52f494266bf1",
        "boundary_type": "wahlbezirk",
        "boundary_year": 2021,
        "code_keys": ("wbz", "WBZ", "wahlbezirk", "Wahlbezirk"),
        "name_keys": (),
    },
    {
        "dataset_id": "fea13bec-d397-40d9-b3de-2bd3030fa248",
        "boundary_type": "wahlbezirk",
        "boundary_year": 2025,
        "code_keys": ("wbz", "WBZ", "wahlbezirk", "Wahlbezirk"),
        "name_keys": (),
    },
]


def _epsg_from_geojson(data: dict[str, Any]) -> int | None:
    """Parse the (legacy) GeoJSON crs member — Leipzig publishes EPSG:25833."""
    name = str(((data.get("crs") or {}).get("properties") or {}).get("name") or "")
    if not name or "CRS84" in name.upper():
        return None
    match = re.search(r"EPSG[:]{1,2}(\d+)", name, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _extract_features(url: str, fmt: str) -> list[dict[str, Any]]:
    """Fetch boundary features as GeoJSON dicts in EPSG:4326."""
    if fmt in ("SHP", "ZIP", "GPKG"):
        with ShapefileExtractor() as ext:
            return ext.extract(url)

    with HttpExtractor() as ext:
        data = ext.get_json(url)
    features = data.get("features", []) if isinstance(data, dict) else []

    epsg = _epsg_from_geojson(data) if isinstance(data, dict) else None
    if epsg and epsg != 4326:
        from pyproj import CRS, Transformer

        transformer = Transformer.from_crs(
            CRS.from_epsg(epsg), CRS.from_epsg(4326), always_xy=True
        )
        for feat in features:
            geom = feat.get("geometry")
            if geom:
                feat["geometry"] = _reproject_feature(geom, transformer)
    return features


def _first_value(props: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        val = props.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def seed_admin_boundaries(contracts: list[dict[str, Any]]) -> int:
    """Ingest all boundary sources into core.admin_boundaries. Returns rows upserted."""
    by_id = {c["id"]: c for c in contracts}
    total = 0

    for source in BOUNDARY_SOURCES:
        contract = by_id.get(source["dataset_id"])
        if not contract:
            logger.error(
                "Boundary contract %s (%s) missing from dataset_contracts.json",
                source["dataset_id"], source["boundary_type"],
            )
            continue

        best = contract.get("best_resource") or {}
        url = best.get("url", "")
        fmt = (best.get("format", "") or "").upper()
        if not url:
            logger.error("Boundary dataset %s has no resource URL", contract["title"])
            continue

        try:
            features = _extract_features(url, fmt)
            total += _upsert_boundaries(source, features)
        except Exception:
            logger.exception(
                "Boundary seeding failed for %s (%s)",
                contract["title"], source["boundary_type"],
            )

    return total


def _upsert_boundaries(source: dict[str, Any], features: list[dict[str, Any]]) -> int:
    btype = source["boundary_type"]
    byear = source["boundary_year"]

    rows: list[tuple] = []
    missing = 0
    for feat in features:
        props = feat.get("properties") or {}
        geom_dict = feat.get("geometry")
        if not geom_dict:
            continue
        code = _first_value(props, source["code_keys"])
        if not code:
            missing += 1
            continue
        name = _first_value(props, source["name_keys"]) or f"{btype.capitalize()} {code}"
        parent = code[0] if source.get("parent_from_first_digit") and len(code) >= 2 else None

        try:
            from shapely.geometry import shape

            geom_wkt = shape(geom_dict).wkt
        except Exception:
            missing += 1
            continue
        rows.append((btype, code, name, geom_wkt, parent, byear))

    if not features:
        raise RuntimeError(f"Boundary source {btype}/{byear}: no features extracted")
    if len(rows) < len(features) * _MIN_CODE_RATIO:
        raise RuntimeError(
            f"Boundary source {btype}/{byear}: only {len(rows)}/{len(features)} "
            f"features yielded a code — property layout changed?"
        )

    with get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO core.admin_boundaries
                        (boundary_type, code, name, geom, parent_code, boundary_year)
                    VALUES (
                        %s, %s, %s,
                        ST_Multi(ST_CollectionExtract(
                            ST_MakeValid(ST_Force2D(ST_GeomFromText(%s, 4326))), 3)),
                        %s, %s
                    )
                    ON CONFLICT (boundary_type, code, boundary_year) DO UPDATE SET
                        name        = EXCLUDED.name,
                        geom        = EXCLUDED.geom,
                        parent_code = EXCLUDED.parent_code
                    """,
                    row,
                )
            # Drop boundaries that vanished from the source so joins stay canonical
            cur.execute(
                """
                DELETE FROM core.admin_boundaries
                WHERE boundary_type = %s AND boundary_year = %s
                  AND code <> ALL(%s)
                """,
                (btype, byear, [r[1] for r in rows]),
            )
        conn.commit()

    logger.info("Boundaries %s/%s: %d features upserted", btype, byear, len(rows))
    return len(rows)


def refresh_spatial_aliases(conn: psycopg.Connection) -> int:
    """Derive name and numeric-variant aliases from the seeded boundaries."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO core.spatial_aliases (unit_type, alias, code, source)
            SELECT DISTINCT ON (boundary_type, alias) boundary_type, alias, code, 'boundary'
            FROM (
                SELECT boundary_type, core.norm_name(name) AS alias, code, boundary_year
                FROM core.admin_boundaries
                WHERE name IS NOT NULL
                UNION ALL
                -- numeric variants: '00' resolvable as '0', '0019' as '19'
                SELECT boundary_type,
                       COALESCE(NULLIF(ltrim(code, '0'), ''), '0'),
                       code, boundary_year
                FROM core.admin_boundaries
                WHERE code ~ '^[0-9]+$'
            ) candidates
            WHERE alias <> ''
            ORDER BY boundary_type, alias, boundary_year DESC
            ON CONFLICT (unit_type, alias) DO UPDATE SET code = EXCLUDED.code
            WHERE spatial_aliases.source = 'boundary'
            """
        )
        count = cur.rowcount
        conn.commit()
    return count


def backfill_spatial_codes(conn: psycopg.Connection) -> int:
    """Resolve raw spatial_key values to canonical codes for existing rows.

    Resolution happens once per distinct (unit, key) pair; rows that stay
    unresolved are retried on the next nightly run (e.g. after manual aliases
    were added to core.spatial_aliases).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH pairs AS (
                SELECT DISTINCT spatial_unit, spatial_key
                FROM core.statistics
                WHERE spatial_unit IN ('ortsteil', 'stadtbezirk', 'wahlbezirk')
                  AND spatial_code IS NULL
            ),
            resolved AS (
                SELECT spatial_unit, spatial_key,
                       core.resolve_spatial_key(spatial_unit, spatial_key) AS code
                FROM pairs
            )
            UPDATE core.statistics s
            SET spatial_code = r.code
            FROM resolved r
            WHERE s.spatial_unit = r.spatial_unit
              AND s.spatial_key  = r.spatial_key
              AND s.spatial_code IS NULL
              AND r.code IS NOT NULL
            """
        )
        updated = cur.rowcount

        cur.execute(
            """
            SELECT COUNT(DISTINCT (spatial_unit, spatial_key)) AS n
            FROM core.statistics
            WHERE spatial_unit IN ('ortsteil', 'stadtbezirk', 'wahlbezirk')
              AND spatial_code IS NULL
            """
        )
        unresolved = cur.fetchone()["n"]
        conn.commit()

    if unresolved:
        logger.warning(
            "spatial_code backfill: %d rows resolved, %d distinct keys unresolved "
            "(add manual rows to core.spatial_aliases)", updated, unresolved,
        )
    else:
        logger.info("spatial_code backfill: %d rows resolved", updated)
    return updated


def seed_boundaries_safe(contracts: list[dict[str, Any]]) -> None:
    """Run the full boundary refresh; never crash the caller."""
    try:
        seed_admin_boundaries(contracts)
        with get_conn() as conn:
            refresh_spatial_aliases(conn)
        with get_conn() as conn:
            backfill_spatial_codes(conn)
    except Exception:
        logger.exception("Boundary seeding failed")
