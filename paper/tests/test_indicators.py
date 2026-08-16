"""Tests for the pure indicator maths.

These are the functions where a mistake is silent: a mis-summed Stadtbezirk or a
share divided by the wrong denominator still produces a plausible correlation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.indicators import aggregate_to_parent, build_counts, compute_shares

ARBEITSLOSE = "30943d88-4ac9-4968-84bc-35e9b337a85d:Arbeitslose insgesamt"
EINWOHNER = "dcc45e1a-11d1-4922-80c3-f49ba12863fb:Einwohner insgesamt"
AUSLAENDER = "dcc45e1a-11d1-4922-80c3-f49ba12863fb:Ausländer"
FAMILIEN = "aa01ad81-1060-48e9-84f2-8908287ecf5e:Familien insgesamt"
ALLEINERZ = "aa01ad81-1060-48e9-84f2-8908287ecf5e:Alleinerziehende insgesamt"


def test_build_counts_keys_by_dataset_and_metric():
    rows = [
        {"spatial_code": "01", "dataset_id": "dcc45e1a-11d1-4922-80c3-f49ba12863fb",
         "metric_name": "Einwohner insgesamt", "metric_value": "1000"},
        {"spatial_code": "01", "dataset_id": "30943d88-4ac9-4968-84bc-35e9b337a85d",
         "metric_name": "Arbeitslose insgesamt", "metric_value": "50"},
    ]
    counts = build_counts(rows)
    assert counts["01"][EINWOHNER] == 1000.0
    assert counts["01"][ARBEITSLOSE] == 50.0


def test_build_counts_does_not_merge_same_metric_name_from_different_datasets():
    """'Ausländer' exists in six datasets with six different base populations."""
    rows = [
        {"spatial_code": "01", "dataset_id": "dcc45e1a-11d1-4922-80c3-f49ba12863fb",
         "metric_name": "Ausländer", "metric_value": "100"},
        {"spatial_code": "01", "dataset_id": "30943d88-4ac9-4968-84bc-35e9b337a85d",
         "metric_name": "Ausländer", "metric_value": "7"},
    ]
    counts = build_counts(rows)
    assert counts["01"][AUSLAENDER] == 100.0
    assert counts["01"]["30943d88-4ac9-4968-84bc-35e9b337a85d:Ausländer"] == 7.0


def test_compute_shares_uses_the_documented_denominators():
    counts = {"01": {EINWOHNER: 1000.0, ARBEITSLOSE: 50.0, AUSLAENDER: 200.0,
                     FAMILIEN: 400.0, ALLEINERZ: 100.0}}
    shares = compute_shares(counts)
    assert shares["01"]["unemployment"] == 0.05
    assert shares["01"]["foreign"] == 0.2
    assert shares["01"]["single_parent"] == 0.25


def test_aggregate_to_parent_sums_counts_not_shares():
    counts = {
        "01": {EINWOHNER: 1000.0, ARBEITSLOSE: 100.0},
        "02": {EINWOHNER: 3000.0, ARBEITSLOSE: 60.0},
        "03": {EINWOHNER: 500.0, ARBEITSLOSE: 5.0},
    }
    parent_of = {"01": "A", "02": "A", "03": "B"}
    agg = aggregate_to_parent(counts, parent_of)
    assert agg["A"][EINWOHNER] == 4000.0
    assert agg["A"][ARBEITSLOSE] == 160.0
    assert agg["B"][EINWOHNER] == 500.0
    # The whole point: the parent share (160/4000 = 4%) is NOT the mean of the
    # child shares (10% and 2% -> 6%). Summing counts first is what makes the
    # MAUP comparison honest.
    parent_share = compute_shares(agg)["A"]["unemployment"]
    assert parent_share == 0.04


def test_aggregate_to_parent_ignores_codes_without_a_parent():
    counts = {"01": {EINWOHNER: 10.0}, "99": {EINWOHNER: 999.0}}
    agg = aggregate_to_parent(counts, {"01": "A"})
    assert agg == {"A": {EINWOHNER: 10.0}}


def test_build_counts_rejects_conflicting_duplicates():
    """Same (spatial_code, dataset_id, metric_name) with different values is an error."""
    rows = [
        {"spatial_code": "01", "dataset_id": "dcc45e1a-11d1-4922-80c3-f49ba12863fb",
         "metric_name": "Einwohner insgesamt", "metric_value": "1000"},
        {"spatial_code": "01", "dataset_id": "dcc45e1a-11d1-4922-80c3-f49ba12863fb",
         "metric_name": "Einwohner insgesamt", "metric_value": "2000"},
    ]
    try:
        build_counts(rows)
    except ValueError:
        return
    raise AssertionError("expected ValueError for conflicting duplicate")


def test_build_counts_allows_identical_duplicates():
    """Same (spatial_code, dataset_id, metric_name) with identical values is okay."""
    rows = [
        {"spatial_code": "01", "dataset_id": "dcc45e1a-11d1-4922-80c3-f49ba12863fb",
         "metric_name": "Einwohner insgesamt", "metric_value": "1000"},
        {"spatial_code": "01", "dataset_id": "dcc45e1a-11d1-4922-80c3-f49ba12863fb",
         "metric_name": "Einwohner insgesamt", "metric_value": "1000"},
    ]
    counts = build_counts(rows)
    assert counts["01"][EINWOHNER] == 1000.0
