from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.correlate import pearson


def test_perfect_positive_correlation():
    result = pearson([1.0, 2.0, 3.0, 4.0], [2.0, 4.0, 6.0, 8.0])
    assert result["n"] == 4
    assert abs(result["r"] - 1.0) < 1e-12
    assert abs(result["r2"] - 1.0) < 1e-12


def test_perfect_negative_correlation():
    result = pearson([1.0, 2.0, 3.0, 4.0], [8.0, 6.0, 4.0, 2.0])
    assert abs(result["r"] + 1.0) < 1e-12
    assert abs(result["r2"] - 1.0) < 1e-12


def test_known_value_hand_computed():
    """xs=[1,2,3,4,5], ys=[2,4,5,4,5] -> r = 0.7745966692414834."""
    result = pearson([1.0, 2.0, 3.0, 4.0, 5.0], [2.0, 4.0, 5.0, 4.0, 5.0])
    assert abs(result["r"] - 0.7745966692414834) < 1e-12
    assert abs(result["r2"] - 0.6) < 1e-12
    assert 0.0 < result["p"] < 0.2


def test_length_mismatch_is_an_error():
    try:
        pearson([1.0, 2.0], [1.0])
    except ValueError:
        return
    raise AssertionError("expected ValueError for mismatched lengths")
