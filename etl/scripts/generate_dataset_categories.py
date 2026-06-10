#!/usr/bin/env python3
"""Generate dataset_categories.json from the opendata.leipzig.de CKAN groups.

The portal maintains 13 DCAT theme groups (German display names). Every one
of our 398 dataset contracts is a CKAN package, so group membership gives a
complete thematic categorization. Strategy: 1 group_list call + 1
package_search per group (14 requests total instead of 398 package_shows).

Output is a committed config (same pattern as dataset_families.json):
review the draft, then commit. Contracts that belong to no CKAN group fall
back to the synthetic category "sonstiges".

Usage:
    python etl/scripts/generate_dataset_categories.py [--contracts PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CKAN_BASE = "https://opendata.leipzig.de/api/3/action"
FALLBACK_ID = "sonstiges"

# statistik.leipzig.de kategorie_nr → DCAT category. Derived from the
# majority co-occurrence of datasets that carry BOTH a CKAN group and a
# kategorie_nr in their API URL (verified 2026-06-10); 12 from the single
# dataset "Straftaten (kleinräumig)".
STATISTIK_KATEGORIE_MAP = {
    1: ["regionen-und-staedte"],
    2: ["bevoelkerung-und-gesellschaft"],
    3: ["bevoelkerung-und-gesellschaft"],
    4: ["bevoelkerung-und-gesellschaft"],
    5: ["bildung-kultur-und-sport"],
    6: ["regionen-und-staedte"],
    7: ["wirtschaft-und-finanzen"],
    8: ["wirtschaft-und-finanzen"],
    9: ["bevoelkerung-und-gesellschaft"],
    10: ["verkehr"],
    11: ["bildung-kultur-und-sport"],
    12: ["justiz-rechtssystem-und-oeffentliche-sicherheit"],
    13: ["umwelt"],
    14: ["regierung-und-oeffentlicher-sektor"],
    15: ["bevoelkerung-und-gesellschaft", "regierung-und-oeffentlicher-sektor"],
}


def slugify(text: str) -> str:
    text = text.lower()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:64]


def _fetch(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.URLError:
        # Fallback for machines with TLS interception where Python's cert
        # store fails but the system curl trust store works.
        import subprocess

        out = subprocess.run(
            ["curl", "-sf", "--max-time", "60", url],
            capture_output=True, check=True,
        )
        return json.loads(out.stdout)


def ckan_get(action: str, **params: str) -> dict:
    url = f"{CKAN_BASE}/{action}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    payload = _fetch(url)
    if not payload.get("success"):
        raise RuntimeError(f"CKAN {action} failed: {payload}")
    return payload["result"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contracts",
        default=Path(__file__).resolve().parents[2] / "dataset_contracts.json",
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    with open(args.contracts, encoding="utf-8") as f:
        contract_ids = {c["id"] for c in json.load(f)}

    groups = ckan_get("group_list", all_fields="true")
    print(f"{len(groups)} CKAN groups", file=sys.stderr)

    categories = []
    memberships: dict[str, list[str]] = {}
    for position, group in enumerate(
        sorted(groups, key=lambda g: g["display_name"]), start=1
    ):
        category_id = slugify(group["display_name"])
        categories.append(
            {
                "category_id": category_id,
                "ckan_name": group["name"],
                "title": group["display_name"],
                "description": (group.get("description") or "").strip() or None,
                "position": position,
            }
        )
        time.sleep(0.5)
        result = ckan_get(
            "package_search",
            fq=f"groups:{group['name']}",
            rows="1000",
            fl="id",
        )
        count = result["count"]
        if count > 1000:
            raise RuntimeError(
                f"group {group['name']} has {count} packages — paging required"
            )
        members = [pkg["id"] for pkg in result["results"]]
        matched = 0
        for pkg_id in members:
            if pkg_id in contract_ids:
                memberships.setdefault(pkg_id, []).append(category_id)
                matched += 1
        print(
            f"  {category_id}: {count} packages, {matched} in contracts",
            file=sys.stderr,
        )

    # ── Enrichment 1: family inheritance ────────────────────────────────────
    # Uncategorized year-variants inherit the categories of their siblings
    # (e.g. "Vornamensstatistik 2022" has no CKAN group, the other years do).
    families_path = Path(args.contracts).parent / "dataset_families.json"
    if families_path.exists():
        with open(families_path, encoding="utf-8") as f:
            families = json.load(f).get("families", [])
        inherited = 0
        for fam in families:
            member_ids = [m["dataset_id"] for m in fam.get("members", [])]
            union = sorted({c for mid in member_ids for c in memberships.get(mid, [])})
            if not union:
                continue
            for mid in member_ids:
                if mid in contract_ids and mid not in memberships:
                    memberships[mid] = union
                    inherited += 1
        print(f"{inherited} contracts categorized via family siblings", file=sys.stderr)

    # ── Enrichment 2: statistik.leipzig.de kategorie_nr ─────────────────────
    with open(args.contracts, encoding="utf-8") as f:
        contracts_full = json.load(f)
    mapped = 0
    for c in contracts_full:
        if c["id"] in memberships:
            continue
        url = (c.get("best_resource") or {}).get("url", "") or ""
        match = re.search(r"kategorie_nr=(\d+)", url)
        if match and "statistik.leipzig.de" in url:
            cats_for_nr = STATISTIK_KATEGORIE_MAP.get(int(match.group(1)))
            if cats_for_nr:
                memberships[c["id"]] = list(cats_for_nr)
                mapped += 1
    print(f"{mapped} contracts categorized via kategorie_nr", file=sys.stderr)

    uncategorized = sorted(contract_ids - set(memberships))
    if uncategorized:
        categories.append(
            {
                "category_id": FALLBACK_ID,
                "ckan_name": None,
                "title": "Sonstiges",
                "description": "Datensätze ohne CKAN-Themenzuordnung",
                "position": 99,
            }
        )
        for dataset_id in uncategorized:
            memberships[dataset_id] = [FALLBACK_ID]
        print(f"{len(uncategorized)} contracts without group → {FALLBACK_ID}", file=sys.stderr)

    out = {"categories": categories, "memberships": dict(sorted(memberships.items()))}
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(
            f"{len(categories)} categories, {len(memberships)} memberships → {args.out}",
            file=sys.stderr,
        )
    else:
        print(text)


if __name__ == "__main__":
    main()
