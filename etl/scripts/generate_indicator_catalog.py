#!/usr/bin/env python3
"""Generate a draft indicator_catalog.json over the statistik.leipzig.de datasets.

Fetches every statistik API dataset (values + kdvalues), melts the
wide-by-year layout with the same transformer the ETL uses, and collects the
indicator names + units. Identical normalized names across datasets fold
into one canonical indicator (e.g. 'Einwohner insgesamt' appears in several
kleinräumig datasets). Topics derive from the dataset's thematic category
(dataset_categories.json); Bevölkerungs-kategorien (kategorie_nr 2/3) get
the dedicated topic 'Demografie'.

The output is a DRAFT — review the folding before committing.

Usage: python etl/scripts/generate_indicator_catalog.py [--out PATH]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "etl"))

from src.extractors.statistik_transform import (  # noqa: E402
    melt_kdvalues, melt_values,
)

_UNIT_SUFFIX = re.compile(r"\s+(in|je)\s+(.+)$", re.IGNORECASE)
DEMOGRAFIE_KATEGORIEN = {2, 3}


def fetch(url: str) -> bytes:
    out = subprocess.run(
        ["curl", "-sfL", "--max-time", "90", url], capture_output=True, check=True
    )
    return out.stdout


def slugify(text: str) -> str:
    text = text.lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:80]


def parse_csv(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace")
    delimiter = ";" if text.split("\n", 1)[0].count(";") > text.split("\n", 1)[0].count(",") else ","
    return [
        {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        for row in csv.DictReader(io.StringIO(text), delimiter=delimiter)
    ]


def metric_names_for(url: str) -> dict[str, str | None]:
    """metric name → unit for one statistik dataset (CSV variant)."""
    rows = parse_csv(fetch(url))
    names: dict[str, str | None] = {}
    if "kdvalues" in url:
        for rec in melt_kdvalues(rows):
            for key in rec:
                if key not in ("Jahr", "Ortsteil"):
                    names.setdefault(key, None)
    else:
        records, units = melt_values(rows)
        for rec in records:
            for key in rec:
                if key != "Jahr":
                    names.setdefault(key, units.get(key))
    return names


def normalize(name: str) -> tuple[str, str | None]:
    """(canonical name, unit hint) — strips trailing 'in %' / 'je 1.000 ...'."""
    name = re.sub(r"\s+", " ", name).strip()
    unit = None
    match = _UNIT_SUFFIX.search(name)
    if match and len(match.group(2)) <= 30:
        unit = match.group(0).strip()[3:].strip() if match.group(1).lower() == "in" else match.group(0).strip()
        name = name[: match.start()].strip(" ,")
    return name, unit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--limit", type=int, default=None, help="nur N Datensätze (Test)")
    args = parser.parse_args()

    with open(REPO / "dataset_contracts.json", encoding="utf-8") as f:
        contracts = json.load(f)
    with open(REPO / "dataset_categories.json", encoding="utf-8") as f:
        categories = json.load(f)
    cat_titles = {c["category_id"]: c["title"] for c in categories["categories"]}
    memberships = categories["memberships"]

    stat_contracts = [
        c for c in contracts
        if "statistik.leipzig.de/opendata/api" in ((c.get("best_resource") or {}).get("url") or "")
    ]
    if args.limit:
        stat_contracts = stat_contracts[: args.limit]
    print(f"{len(stat_contracts)} statistik-Datensätze", file=sys.stderr)

    # ── Pass 1: Kennzahlen je Datensatz einsammeln ───────────────────────────
    def title_stem(title: str) -> str:
        return re.sub(r"\s*\(.*?\)\s*$", "", title).strip()

    collected: list[dict] = []  # {dataset_id, title_stem, topic, raw_name, canonical, unit}
    for i, contract in enumerate(stat_contracts, 1):
        url = contract["best_resource"]["url"]
        try:
            names = metric_names_for(url)
        except Exception as exc:
            print(f"  [{i}] FEHLER {contract['title']}: {exc}", file=sys.stderr)
            continue

        kat_match = re.search(r"kategorie_nr=(\d+)", url)
        kat_nr = int(kat_match.group(1)) if kat_match else None
        if kat_nr in DEMOGRAFIE_KATEGORIEN:
            topic = "Demografie"
        else:
            cats = memberships.get(contract["id"], [])
            topic = cat_titles.get(cats[0], "Sonstiges") if cats else "Sonstiges"

        for raw_name, unit in names.items():
            canonical, unit_hint = normalize(raw_name)
            if not canonical:
                continue
            collected.append({
                "dataset_id": contract["id"],
                "stem": title_stem(contract["title"]),
                "topic": topic,
                "raw_name": raw_name,
                "canonical": canonical,
                "unit": unit or unit_hint,
            })
        print(f"  [{i}/{len(stat_contracts)}] {contract['title']}: {len(names)} Kennzahlen", file=sys.stderr)
        time.sleep(0.2)

    # ── Pass 2: Faltung — mehrdeutige Namen mit Titel-Stamm disambiguieren ──
    # 'Frauen' in 'Arbeitslose (kleinräumig)' ≠ 'Frauen' in 'Einwohner ...';
    # gleiche Namen werden nur gefaltet, wenn alle Quellen denselben
    # Titel-Stamm teilen (z. B. Jahres- + Quartalsreihe desselben Themas).
    stems_per_name: dict[str, set[str]] = defaultdict(set)
    for entry in collected:
        stems_per_name[entry["canonical"]].add(entry["stem"])

    indicators: dict[str, dict] = {}
    for entry in collected:
        ambiguous = len(stems_per_name[entry["canonical"]]) > 1
        display = (
            f"{entry['stem']}: {entry['canonical']}" if ambiguous else entry["canonical"]
        )
        ind = indicators.setdefault(
            slugify(display),
            {"name": display, "unit": None, "topics": defaultdict(int), "metrics": []},
        )
        ind["metrics"].append(
            {"dataset_id": entry["dataset_id"], "metric_name": entry["raw_name"]}
        )
        ind["topics"][entry["topic"]] += 1
        if ind["unit"] is None:
            ind["unit"] = entry["unit"]

    out = {
        "indicators": [
            {
                "indicator_id": ind_id,
                "name": ind["name"],
                "unit": ind["unit"],
                "topic": max(ind["topics"], key=ind["topics"].get),
                "metrics": ind["metrics"],
            }
            for ind_id, ind in sorted(indicators.items())
        ]
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        merged = sum(1 for i in out["indicators"] if len(i["metrics"]) > 1)
        print(
            f"{len(out['indicators'])} Indikatoren ({merged} mit >1 Quelle) → {args.out}",
            file=sys.stderr,
        )
    else:
        print(text)


if __name__ == "__main__":
    main()
