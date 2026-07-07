"""Links-Rechts-Score über Parteianteils-Verteilungen (Sitzordnung Bundestag).

Rein funktional (kein DB/FastAPI-Import) — unit-testbar ohne Umgebung.
"""

from __future__ import annotations

SONSTIGE_COLOR = "#6b7683"


def compute_spectrum(rows: list[dict]) -> dict:
    """Score + aufbereitete Parteiliste für EIN Gebiet.

    rows: [{key, name, position, color, share}] — position None = nicht kodiert,
    share kann None/Decimal sein (SQL-Numerics).
    """
    mapped: list[dict] = []
    sonstige_share = 0.0
    for r in rows:
        if r.get("share") is None:
            continue
        share = float(r["share"])
        if r.get("position") is not None:
            mapped.append(
                {
                    "key": r["key"],
                    "name": r["name"],
                    "share": share,
                    "color": r["color"],
                    "position": float(r["position"]),
                }
            )
        else:
            sonstige_share += share

    coverage = sum(p["share"] for p in mapped)
    score = (
        sum(p["position"] * p["share"] for p in mapped) / coverage
        if coverage > 0
        else None
    )

    parties = [
        {"key": p["key"], "name": p["name"], "share": round(p["share"], 2), "color": p["color"]}
        for p in sorted(mapped, key=lambda p: -p["share"])
    ]
    if sonstige_share > 0:
        parties.append(
            {"key": None, "name": "Sonstige", "share": round(sonstige_share, 2), "color": SONSTIGE_COLOR}
        )

    return {
        "score": round(score, 4) if score is not None else None,
        "coverage_pct": round(coverage, 2),
        "parties": parties,
    }
