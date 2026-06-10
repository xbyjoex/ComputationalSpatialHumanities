#!/usr/bin/env python3
"""Derive the party order of the 'Offene Wahldaten' CSV columns per election.

The standardized election CSVs carry per-party votes in anonymous columns
D1..Dn (Erststimmen) / F1..Fn (Zweitstimmen) in official ballot order, with
no definition file. statistik.leipzig.de however publishes the same final
results WITH party names (kategorie 15, share of valid votes). This script
matches each column's city-total share against those named shares and emits
a draft election_definitions.json.

Every match is printed with its delta — review before committing. Columns
without a confident match are flagged "UNMATCHED-Di" and must be curated by
hand.

Usage: python etl/scripts/generate_election_definitions.py [--out PATH]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path

STAT_API = "https://statistik.leipzig.de/opendata/api/values"

# Stadt-CSV + statistik rubrik per election. vote_col: which letter carries
# the party votes ('F' = Zweitstimmen for erst_zweit elections, 'D' for
# single-vote elections); the statistik shares refer to exactly that vote.
ELECTIONS = [
    {
        "election_id": "btw2021",
        "title": "Bundestagswahl 2021",
        "election_type": "bundestagswahl",
        "date": "2021-09-26",
        "year": 2021,
        "vote_mode": "erst_zweit",
        "vote_col": "F",
        "rubrik_nr": 2,
        "stat_jahr": "26.09.2021",
        "stadt_csv": "https://opendata.leipzig.de/dataset/fff8cfc0-a4aa-4627-89ed-a46bb6a29c59/resource/8322e9af-940c-4b71-a2f4-fc1f1c0aa4b0/download/open-data-bundestagswahl-_land-sachsen_3-1.csv",
        "datasets": {
            "fff8cfc0-a4aa-4627-89ed-a46bb6a29c59": {"level": "stadt"},
            "f5b27739-e3dd-49ca-95cd-9b0e9b907684": {"level": "wahlbezirk"},
            "8354f558-9291-44a4-b487-35577e5ea2ec": {"level": "ortsteil"},
        },
    },
    {
        "election_id": "btw2025",
        "title": "Bundestagswahl 2025",
        "election_type": "bundestagswahl",
        "date": "2025-02-23",
        "year": 2025,
        "vote_mode": "erst_zweit",
        "vote_col": "F",
        "rubrik_nr": 2,
        "stat_jahr": "23.02.2025",
        "stadt_csv": "https://wahlergebnis.leipzig.de/4/bt2025/14713000/daten/opendata/Open-Data-14713000-Bundestagswahl-Stadtgebiet.csv",
        "datasets": {
            "510a0409-744b-4462-87ec-832057c1df38": {"level": "stadt"},
            "19ea44b0-1d0f-4e4e-b6e4-4f4d5bcc0c90": {"level": "wahlbezirk"},
        },
    },
    {
        "election_id": "ew2024",
        "title": "Europawahl 2024",
        "election_type": "europawahl",
        "date": "2024-06-09",
        "year": 2024,
        "vote_mode": "single",
        "vote_col": "D",
        "rubrik_nr": 1,
        "stat_jahr": "09.06.2024",
        "stadt_csv": "https://opendata.leipzig.de/dataset/4b9c85a0-63a1-406f-923e-1df14295f3ed/resource/33ab8ced-6d3e-40c7-8206-d6c2af1c0739/download/open-data-14713000-europawahl-stadtgebiet.csv",
        "datasets": {
            "4b9c85a0-63a1-406f-923e-1df14295f3ed": {"level": "stadt"},
            "bf7b851d-592c-425c-9f11-704966305147": {"level": "wahlbezirk"},
            "0e7e9fa6-5d6a-4301-b991-5dad6c6f027e": {"level": "ortsteil"},
            "c1bac74a-cdd2-4116-8ba9-ff2c2c7aa6b0": {"level": "stadtbezirk"},
        },
    },
    {
        "election_id": "ltw2024",
        "title": "Landtagswahl 2024",
        "election_type": "landtagswahl",
        "date": "2024-09-01",
        "year": 2024,
        "vote_mode": "erst_zweit",
        "vote_col": "F",
        "rubrik_nr": 3,
        "stat_jahr": "01.09.2024",
        "stadt_csv": "https://opendata.leipzig.de/dataset/5be18d85-d375-4849-9a8b-8c222f53c1d4/resource/99829035-e209-4beb-ae66-e5d9fa3c45a9/download/open-data-14713000-wahl-des-saechsischen-landtages-stadtgebiet.csv",
        "datasets": {
            "5be18d85-d375-4849-9a8b-8c222f53c1d4": {"level": "stadt"},
            "4db3895e-92a9-4bb7-bb33-f792178d331f": {"level": "wahlbezirk"},
            "3700e4dc-bb3e-483c-b285-f25b1aea806e": {"level": "ortsteil"},
        },
    },
    {
        "election_id": "srw2024",
        "title": "Stadtratswahl 2024",
        "election_type": "stadtratswahl",
        "date": "2024-06-09",
        "year": 2024,
        # Kommunalwahl: 3 Stimmen je Wähler:in, Parteisummen in E1..En,
        # Bewerber-Unterspalten E{i}_{j} werden ignoriert.
        "vote_mode": "kommunal",
        "vote_col": "E",
        "rubrik_nr": 4,
        "stat_jahr": "09.06.2024",
        "stadt_csv": "https://opendata.leipzig.de/dataset/b03dcd68-b921-4356-b2b8-5f28669e8e50/resource/e0bff748-39d2-4453-90ca-277247ee4c88/download/open-data-14713000-stadtratswahl-leipzig-stadtgebiet.csv",
        "datasets": {
            "b03dcd68-b921-4356-b2b8-5f28669e8e50": {"level": "stadt"},
            "1ae46e0e-af40-439e-9ad8-eb5abf81679d": {"level": "wahlbezirk"},
            "4f261ede-a4c6-4815-a773-6d975c0a8ae5": {"level": "ortsteil"},
        },
    },
]


def fetch(url: str) -> bytes:
    out = subprocess.run(
        ["curl", "-sfL", "--max-time", "60", url], capture_output=True, check=True
    )
    return out.stdout


def stat_shares(rubrik_nr: int, stat_jahr: str) -> dict[str, float]:
    """Named party → share of valid votes (%) from statistik.leipzig.de."""
    raw = fetch(f"{STAT_API}?kategorie_nr=15&rubrik_nr={rubrik_nr}&periode=d&format=json")
    data = json.loads(raw)
    rows = data if isinstance(data, list) else data.get("values", data.get("data", []))
    shares: dict[str, float] = {}
    for row in rows:
        if str(row.get("jahr")) != stat_jahr:
            continue
        try:
            shares[str(row["name"])] = float(str(row.get("wert")).replace(",", "."))
        except (ValueError, TypeError):
            continue  # 'x' = nicht angetreten / unterdrückt
    return shares


def csv_party_shares(url: str, vote_col: str) -> tuple[list[tuple[int, float]], dict]:
    """Per-column share of valid votes from the Stadt-CSV (single data row)."""
    text = fetch(url).decode("utf-8-sig", errors="replace")
    delimiter = ";" if text.split("\n", 1)[0].count(";") >= text.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rec = next(reader)
    rec = {k.strip(): (v.strip() if v else "") for k, v in rec.items() if k}

    valid = float(rec[vote_col])  # D/F/E = gültige Stimmen gesamt
    shares = []
    i = 1
    while f"{vote_col}{i}" in rec:
        raw = rec.get(f"{vote_col}{i}", "")
        votes = float(raw) if raw else 0.0
        shares.append((i, votes / valid * 100))
        i += 1
    return shares, rec


def match_parties(
    cols: list[tuple[int, float]], named: dict[str, float]
) -> list[str]:
    parties = []
    used: set[str] = set()
    for idx, share in cols:
        best, best_delta = None, 99.0
        for name, ref in named.items():
            if name in used:
                continue
            delta = abs(ref - share)
            if delta < best_delta:
                best, best_delta = name, delta
        if best is not None and best_delta < 0.02:
            parties.append(best)
            used.add(best)
            print(f"    D/F{idx}: {best:<28} csv={share:.4f}%  amtlich={named[best]:.4f}%  Δ={best_delta:.4f}", file=sys.stderr)
        else:
            # Kleinstpartei, die die amtliche Statistik nur unter 'Sonstige'
            # führt — kein verifizierbarer Name, transparentes Label.
            # (Plan-Regel: ohne amtlichen Abgleich keine Namens-Übernahme.)
            parties.append(f"Liste {idx}")
            print(f"    D/F{idx}: Liste {idx}  csv={share:.4f}%  (unverifiziert, bester Kandidat: {best} Δ={best_delta:.4f})", file=sys.stderr)
    return parties


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    out_elections = []
    for e in ELECTIONS:
        print(f"\n== {e['title']} ==", file=sys.stderr)
        named = stat_shares(e["rubrik_nr"], e["stat_jahr"])
        print(f"  amtliche Parteien: {len(named)}", file=sys.stderr)
        cols, _ = csv_party_shares(e["stadt_csv"], e["vote_col"])
        parties = match_parties(cols, named)
        out_elections.append(
            {
                "election_id": e["election_id"],
                "title": e["title"],
                "election_type": e["election_type"],
                "date": e["date"],
                "year": e["year"],
                "vote_mode": e["vote_mode"],
                "parties": parties,
                "datasets": e["datasets"],
            }
        )

    text = json.dumps({"elections": out_elections}, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"\n→ {args.out}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
