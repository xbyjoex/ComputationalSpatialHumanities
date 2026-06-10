#!/usr/bin/env python3
"""Generate a draft dataset_families.json from dataset_contracts.json.

Groups datasets whose titles differ only by a year (e.g. "Vornamenstatistik
2024" / "Vornamenstatistik 2025") into families. The output is a DRAFT:
review it manually (merge spelling variants, assign years to undated members,
delete false positives) before committing it as dataset_families.json.

Usage:
    python etl/scripts/generate_dataset_families.py [--contracts PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

YEAR_RE = re.compile(r"\b(19|20)\d{2}(?:\s*/\s*(?:\d{2}|\d{4}))?\b")

# Known spelling variants folded before grouping
TITLE_FOLDS = {
    "vornamensstatistik": "vornamenstatistik",
}


def base_title(title: str) -> tuple[str, int | None]:
    """Strip the year from a title, return (normalized base, year or None)."""
    match = YEAR_RE.search(title)
    year = int(match.group(0)[:4]) if match else None
    base = YEAR_RE.sub(" ", title)
    base = re.sub(r"[\s\-–—:,/]+", " ", base).strip().lower()
    for variant, canonical in TITLE_FOLDS.items():
        base = base.replace(variant, canonical)
    return base, year


def slugify(text: str) -> str:
    text = text.lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:64]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contracts",
        default=Path(__file__).resolve().parents[2] / "dataset_contracts.json",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    with open(args.contracts, encoding="utf-8") as f:
        contracts = json.load(f)

    groups: dict[str, list[dict]] = defaultdict(list)
    for c in contracts:
        base, year = base_title(c["title"])
        groups[base].append({"dataset_id": c["id"], "title": c["title"], "year": year})

    families = []
    for base, members in sorted(groups.items()):
        dated = [m for m in members if m["year"] is not None]
        if len(members) < 2 or not dated:
            continue
        title = re.sub(
            YEAR_RE, "", min((m["title"] for m in dated), key=len)
        )
        title = re.sub(r"[\s\-–—:,/]+$", "", re.sub(r"\s+", " ", title)).strip(" -:,")
        family_members = []
        for m in sorted(members, key=lambda m: (m["year"] or 0, m["title"])):
            entry = {"dataset_id": m["dataset_id"], "year": m["year"], "title": m["title"]}
            if m["year"] is None:
                entry["needs_review"] = True
            family_members.append(entry)
        families.append(
            {"family_id": slugify(base), "title": title, "members": family_members}
        )

    out = {"families": families, "dataset_hints": {}}
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"{len(families)} families written to {args.out}", file=sys.stderr)
    else:
        print(text)
        print(f"-- {len(families)} families detected", file=sys.stderr)


if __name__ == "__main__":
    main()
