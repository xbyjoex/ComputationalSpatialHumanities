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


def parent_map(rows: list[dict]) -> dict[str, str]:
    """{ortsteil_code: stadtbezirk_code} from core.admin_boundaries."""
    return {
        r["code"]: r["parent_code"]
        for r in rows
        if r["boundary_type"] == "ortsteil" and r["parent_code"]
    }


def official_stadtbezirk_counts(rows: list[dict]) -> dict[str, dict[str, float]]:
    """The city's own Stadtbezirk figures, used only to validate our sums."""
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        key = metric_key(row["dataset_id"], row["metric_name"])
        out.setdefault(row["stadtbezirk_code"], {})[key] = float(row["metric_value"])
    return out


def validate_aggregation(ours, official) -> dict:
    """Compare our Ortsteil sums against the official Stadtbezirk rows."""
    checks = []
    for code, metrics in sorted(ours.items()):
        for key, value in sorted(metrics.items()):
            reference = official.get(code, {}).get(key)
            if reference is None:
                continue
            checks.append({
                "stadtbezirk": code,
                "metric": key,
                "ours": value,
                "official": reference,
                "delta": value - reference,
            })
    mismatches = [c for c in checks if abs(c["delta"]) > 0.5]
    return {"compared": len(checks), "mismatches": mismatches}


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

    results_ot = correlate_grid(votes_ot, shares, codes_ot)

    parents = parent_map(read_csv("boundaries.csv"))
    counts_sb = aggregate_to_parent(counts, parents)
    shares_sb = compute_shares(counts_sb)
    votes_sb = party_shares(read_csv("election_stadtbezirk.csv"))
    codes_sb = sorted(set(counts_sb) & set(votes_sb))

    if len(counts_sb) != EXPECTED_STADTBEZIRKE:
        raise SystemExit(
            f"aggregated to {len(counts_sb)} Stadtbezirke, expected {EXPECTED_STADTBEZIRKE}"
        )

    validation = validate_aggregation(
        counts_sb, official_stadtbezirk_counts(read_csv("indicators_stadtbezirk_raw.csv"))
    )
    if validation["mismatches"]:
        raise SystemExit(
            f"aggregation disagrees with the official Stadtbezirk figures in "
            f"{len(validation['mismatches'])} of {validation['compared']} checks: "
            f"{validation['mismatches'][:3]}"
        )

    corr_sb = correlate_grid(votes_sb, shares_sb, codes_sb)

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
            "correlations": results_ot,
        },
        "stadtbezirk": {
            "n": len(codes_sb),
            "shares": {c: shares_sb[c] for c in codes_sb},
            "votes": {c: votes_sb[c] for c in codes_sb},
            "correlations": corr_sb,
        },
        "maup": {
            key: {
                "ortsteil": results_ot[key],
                "stadtbezirk": corr_sb[key],
                "delta_r": corr_sb[key]["r"] - results_ot[key]["r"],
            }
            for key in sorted(set(results_ot) & set(corr_sb))
        },
        "validation": validation,
    }

    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT} — n={len(codes_ot)} Ortsteile")
    for key, stat in sorted(
        results["ortsteil"]["correlations"].items(),
        key=lambda kv: -abs(kv[1]["r"]),
    )[:8]:
        print(f"  {key:<28} r={stat['r']:+.3f}  R²={stat['r2']:.3f}  p={stat['p']:.2e}")

    print(f"\nMAUP — same pairing, Ortsteil (n={len(codes_ot)}) vs Stadtbezirk (n={len(codes_sb)}):")
    for key, cmp in sorted(results["maup"].items(), key=lambda kv: -abs(kv[1]["delta_r"]))[:8]:
        print(
            f"  {key:<28} r={cmp['ortsteil']['r']:+.3f} -> {cmp['stadtbezirk']['r']:+.3f}"
            f"  Δr={cmp['delta_r']:+.3f}"
        )
    print(f"\naggregation validated against {results['validation']['compared']} official figures")


if __name__ == "__main__":
    main()
