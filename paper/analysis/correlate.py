"""Pearson correlation with the numbers the paper reports."""

from __future__ import annotations

from scipy import stats


def pearson(xs, ys) -> dict:
    """Return r, R^2, two-sided p and n for two equal-length samples."""
    if len(xs) != len(ys):
        raise ValueError(f"length mismatch: {len(xs)} vs {len(ys)}")
    if len(xs) < 3:
        raise ValueError(f"need at least 3 pairs, got {len(xs)}")
    result = stats.pearsonr(xs, ys)
    r = float(result.statistic)
    return {"r": r, "r2": r * r, "p": float(result.pvalue), "n": len(xs)}
