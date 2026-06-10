"""Election domain: semantic loader for the 'Offene Wahldaten' CSVs.

Column semantics per the standard: A=Wahlberechtigte, B=Wähler:innen,
B1=Briefwähler:innen, C/E=ungültige, D/F=gültige Erst-/Zweitstimmen,
D{i}/F{i}=Stimmen je Partei i in amtlicher Listenreihenfolge. Kommunalwahlen
(vote_mode='kommunal') führen Parteisummen stattdessen in E{i} (3 Stimmen je
Wähler:in); Bewerber-Unterspalten E{i}_{j} werden ignoriert.

The party order per election comes from election_definitions.json — derived
and verified against the named shares of the statistik.leipzig.de API by
etl/scripts/generate_election_definitions.py. Unverified micro parties carry
the transparent label "Liste {i}".
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import psycopg

from ..config import settings
from ..db import get_conn
from ..extractors.csv_extractor import CsvExtractor
from ..loaders.postgres import _resolve_spatial_codes, _safe_int

logger = logging.getLogger(__name__)

_BATCH = 500
_RESOLVABLE_LEVELS = ("wahlbezirk", "ortsteil", "stadtbezirk")

_definitions: dict[str, Any] | None = None
_routes: dict[str, tuple[dict[str, Any], str]] | None = None


def load_definitions() -> dict[str, Any]:
    global _definitions
    if _definitions is not None:
        return _definitions
    path = Path(settings.elections_path)
    if not path.exists():
        repo_root = Path(__file__).resolve().parents[3] / "election_definitions.json"
        path = repo_root if repo_root.exists() else path
    if not path.exists():
        logger.warning("No election_definitions.json found — election domain disabled")
        _definitions = {"elections": []}
        return _definitions
    with open(path, encoding="utf-8") as f:
        _definitions = json.load(f)
    logger.info("Loaded %d election definitions", len(_definitions.get("elections", [])))
    return _definitions


def route_for(dataset_id: str) -> tuple[dict[str, Any], str] | None:
    """(election definition, level) if this dataset is an election result set."""
    global _routes
    if _routes is None:
        _routes = {}
        for election in load_definitions().get("elections", []):
            for ds_id, spec in election.get("datasets", {}).items():
                _routes[ds_id] = (election, spec["level"])
    return _routes.get(dataset_id)


def _vote_columns(vote_mode: str) -> tuple[str, str, str]:
    """(party column letter, ungültige column, gültige column)."""
    if vote_mode == "erst_zweit":
        return "F", "E", "F"
    if vote_mode == "kommunal":
        return "E", "C", "E"
    return "D", "C", "D"  # single


def run_election_dataset(
    contract: dict[str, Any], url: str, election: dict[str, Any], level: str
) -> tuple[int, int, str]:
    with CsvExtractor() as ext:
        records = ext.extract_all(url)

    election_id = election["election_id"]
    vote_mode = election["vote_mode"]
    parties: list[str] = election["parties"]
    party_col, _, _ = _vote_columns(vote_mode)

    rows: list[list[Any]] = []
    for rec in records:
        gebiet_nr = (rec.get("gebiet-nr") or "").strip()
        gebiet_name = (rec.get("gebiet-name") or "").strip()
        if level == "stadt":
            gebiet_code = "leipzig"
            gebiet_name = gebiet_name or "Stadt Leipzig"
        elif level == "wahlbezirk":
            if not gebiet_nr:
                continue
            gebiet_code = gebiet_nr.zfill(4)
        else:  # ortsteil / stadtbezirk: Schlüssel ist der Name (gebiet-nr leer)
            gebiet_code = gebiet_nr or gebiet_name
            if not gebiet_code:
                continue

        wahlberechtigte = _safe_int(rec.get("A"))
        waehler = _safe_int(rec.get("B"))
        briefwaehler = _safe_int(rec.get("B1"))
        if vote_mode == "erst_zweit":
            ungueltige_erst = _safe_int(rec.get("C"))
            gueltige_erst = _safe_int(rec.get("D"))
            ungueltige_zweit = _safe_int(rec.get("E"))
            gueltige_zweit = _safe_int(rec.get("F"))
        else:
            ungueltige_erst = None
            gueltige_erst = None
            ungueltige_zweit = _safe_int(rec.get("C"))
            gueltige_zweit = _safe_int(rec.get("D" if vote_mode == "single" else "E"))

        for i, party in enumerate(parties, start=1):
            if vote_mode == "erst_zweit":
                erst = _safe_int(rec.get(f"D{i}"))
                zweit = _safe_int(rec.get(f"F{i}"))
            else:
                erst = None
                zweit = _safe_int(rec.get(f"{party_col}{i}"))
            rows.append([
                election_id, contract["id"], level, gebiet_code, gebiet_name or None,
                None,  # spatial_code, gefüllt unten
                party, i, erst, zweit,
                wahlberechtigte, waehler, briefwaehler,
                ungueltige_erst, gueltige_erst, ungueltige_zweit, gueltige_zweit,
            ])

    loaded = 0
    with get_conn() as conn:
        # Kanonische Boundary-Codes: Wahlbezirke joinen die Wahl-Geometrien
        # (boundary_year), Ortsteile/Stadtbezirke über Namens-Aliase. Stadt &
        # Briefwahlbezirke bleiben NULL — keine Geometrie, Summen unberührt.
        if level in _RESOLVABLE_LEVELS:
            pairs = sorted({(level, r[3]) for r in rows})
            code_map = _resolve_spatial_codes(conn, pairs)
            for r in rows:
                r[5] = code_map.get((level, r[3]))

        with conn.cursor() as cur:
            for i in range(0, len(rows), _BATCH):
                batch = [tuple(r) for r in rows[i : i + _BATCH]]
                cur.executemany(
                    """
                    INSERT INTO core.election_results
                        (election_id, dataset_id, level, gebiet_code, gebiet_name,
                         spatial_code, party, party_index, erststimmen, zweitstimmen,
                         wahlberechtigte, waehler, briefwaehler,
                         ungueltige_erst, gueltige_erst, ungueltige_zweit, gueltige_zweit)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (election_id, level, gebiet_code, party) DO UPDATE SET
                        dataset_id       = EXCLUDED.dataset_id,
                        gebiet_name      = EXCLUDED.gebiet_name,
                        spatial_code     = EXCLUDED.spatial_code,
                        party_index      = EXCLUDED.party_index,
                        erststimmen      = EXCLUDED.erststimmen,
                        zweitstimmen     = EXCLUDED.zweitstimmen,
                        wahlberechtigte  = EXCLUDED.wahlberechtigte,
                        waehler          = EXCLUDED.waehler,
                        briefwaehler     = EXCLUDED.briefwaehler,
                        ungueltige_erst  = EXCLUDED.ungueltige_erst,
                        gueltige_erst    = EXCLUDED.gueltige_erst,
                        ungueltige_zweit = EXCLUDED.ungueltige_zweit,
                        gueltige_zweit   = EXCLUDED.gueltige_zweit,
                        ingested_at      = NOW()
                    """,
                    batch,
                )
                loaded += len(batch)
        conn.commit()

    return len(records), loaded, "core.election_results"


def sync_elections(conn: psycopg.Connection, config: dict[str, Any]) -> int:
    """Sync core.elections and clean up legacy representations.

    Election result sets used to flow into core.statistics as anonymous
    D1/F1 metrics via dataset_hints — those rows are deleted here so they
    disappear from the metric pickers after the next mart refresh.
    """
    elections = config.get("elections", [])
    dataset_ids = [ds for e in elections for ds in e.get("datasets", {})]

    with conn.cursor() as cur:
        for e in elections:
            cur.execute(
                """
                INSERT INTO core.elections
                    (election_id, title, election_type, election_date, year, vote_mode)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (election_id) DO UPDATE SET
                    title         = EXCLUDED.title,
                    election_type = EXCLUDED.election_type,
                    election_date = EXCLUDED.election_date,
                    year          = EXCLUDED.year,
                    vote_mode     = EXCLUDED.vote_mode,
                    updated_at    = NOW()
                """,
                (e["election_id"], e["title"], e["election_type"],
                 e.get("date"), e["year"], e["vote_mode"]),
            )
            # Umbenannte/entfernte Parteien aus früheren Config-Ständen räumen
            cur.execute(
                "DELETE FROM core.election_results WHERE election_id = %s AND party <> ALL(%s)",
                (e["election_id"], e["parties"]),
            )

        if dataset_ids:
            cur.execute(
                "DELETE FROM core.statistics WHERE dataset_id = ANY(%s)",
                (dataset_ids,),
            )
            if cur.rowcount:
                logger.info(
                    "Removed %d legacy statistics rows for election datasets",
                    cur.rowcount,
                )
        conn.commit()
    return len(elections)
