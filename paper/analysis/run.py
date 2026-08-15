#!/usr/bin/env python3
"""Turn the extracted CSVs into results.json — the single source of every number
that appears in the paper.

Run after paper/analysis/extract.sh. Fails loudly on any implausible input
rather than producing a number nobody checks.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from indicators import (
    EINWOHNER,
    aggregate_to_parent,
    build_counts,
    compute_shares,
    metric_key,
)
from correlate import pearson

DATA = Path(__file__).parent / "data"
OUT = Path(__file__).parent / "results.json"

YEAR = 2024
ELECTION = "ew2024"
EXPECTED_POPULATION = 632560
EXPECTED_ORTSTEILE = 63
EXPECTED_STADTBEZIRKE = 10

# Reported parties. Several, not one: the case study is a method demonstration,
# and singling out a party would read as a political statement instead.
PARTIES = ["CDU", "AfD", "DIE LINKE", "GRÜNE", "SPD", "BSW"]
SHARES = ["unemployment", "foreign", "single_parent"]


def read_csv(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def party_shares(rows: list[dict]) -> dict[str, dict[str, float]]:
    """{spatial_code: {party: vote share}} plus a 'turnout' pseudo-party."""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        code = row["spatial_code"]
        valid = float(row["gueltige_zweit"] or 0)
        if valid == 0:
            continue
        bucket = out.setdefault(code, {})
        bucket[row["party"]] = float(row["zweitstimmen"] or 0) / valid
        eligible = float(row["wahlberechtigte"] or 0)
        if eligible:
            bucket["turnout"] = float(row["waehler"] or 0) / eligible
    return out


def correlate_grid(votes, shares, codes) -> dict:
    """Every reported party against every indicator, over the given codes."""
    grid: dict[str, dict] = {}
    for party in PARTIES + ["turnout"]:
        for share in SHARES:
            pairs = [
                (shares[c][share], votes[c][party])
                for c in codes
                if c in shares and c in votes
                and share in shares[c] and party in votes[c]
            ]
            if len(pairs) < 3:
                continue
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            grid[f"{party}|{share}"] = pearson(xs, ys)
    return grid


def main() -> None:
    ind_rows = read_csv("indicators_ortsteil.csv")
    counts = build_counts(ind_rows)
    shares = compute_shares(counts)

    population = sum(m.get(EINWOHNER, 0.0) for m in counts.values())
    if round(population) != EXPECTED_POPULATION:
        raise SystemExit(
            f"population sum is {population:,.0f}, expected {EXPECTED_POPULATION:,}. "
            "Migration 018 is probably not applied — stop and fix that first."
        )
    if len(counts) != EXPECTED_ORTSTEILE:
        raise SystemExit(f"got {len(counts)} Ortsteile, expected {EXPECTED_ORTSTEILE}")

    votes_ot = party_shares(read_csv("election_ortsteil.csv"))
    codes_ot = sorted(set(counts) & set(votes_ot))

    results = {
        "meta": {
            "year": YEAR,
            "election": ELECTION,
            "parties": PARTIES,
            "indicators": SHARES,
            "population_checked": EXPECTED_POPULATION,
        },
        "ortsteil": {
            "n": len(codes_ot),
            "shares": {c: shares[c] for c in codes_ot},
            "votes": {c: votes_ot[c] for c in codes_ot},
            "correlations": correlate_grid(votes_ot, shares, codes_ot),
        },
    }

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} — n={len(codes_ot)} Ortsteile")
    for key, stat in sorted(
        results["ortsteil"]["correlations"].items(),
        key=lambda kv: -abs(kv[1]["r"]),
    )[:8]:
        print(f"  {key:<28} r={stat['r']:+.3f}  R²={stat['r2']:.3f}  p={stat['p']:.2e}")


if __name__ == "__main__":
    main()
