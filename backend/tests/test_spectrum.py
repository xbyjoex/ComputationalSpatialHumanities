from decimal import Decimal

from src.api.spectrum import SONSTIGE_COLOR, compute_spectrum


def _p(key, position, share, name=None, color="#fff"):
    return {"key": key, "name": name or key, "position": position, "color": color, "share": share}


def test_score_is_share_weighted_mean_over_mapped_parties():
    rows = [_p("linke", -1.0, 50.0), _p("cdu", 0.6, 50.0)]
    out = compute_spectrum(rows)
    assert out["score"] == -0.2          # (-1*50 + 0.6*50) / 100
    assert out["coverage_pct"] == 100.0


def test_unmapped_parties_aggregate_to_sonstige_and_dont_move_score():
    rows = [
        _p("linke", -1.0, 40.0),
        _p(None, None, 5.5, name="Die PARTEI"),
        _p(None, None, 4.5, name="Liste 12"),
    ]
    out = compute_spectrum(rows)
    assert out["score"] == -1.0          # nur linke ist gemappt
    assert out["coverage_pct"] == 40.0
    sonstige = out["parties"][-1]
    assert sonstige == {"key": None, "name": "Sonstige", "share": 10.0, "color": SONSTIGE_COLOR}


def test_parties_sorted_by_share_desc_mapped_first():
    rows = [_p("spd", -0.25, 10.0), _p("afd", 1.0, 30.0), _p(None, None, 50.0, name="X")]
    out = compute_spectrum(rows)
    assert [p["name"] for p in out["parties"]] == ["afd", "spd", "Sonstige"]


def test_all_unmapped_gives_null_score():
    out = compute_spectrum([_p(None, None, 60.0, name="X")])
    assert out["score"] is None
    assert out["coverage_pct"] == 0.0


def test_empty_input():
    out = compute_spectrum([])
    assert out == {"score": None, "coverage_pct": 0.0, "parties": []}


def test_decimal_and_none_shares_are_tolerated():
    rows = [_p("cdu", 0.6, Decimal("25.5")), _p("spd", -0.25, None)]
    out = compute_spectrum(rows)
    assert out["score"] == 0.6
    assert out["coverage_pct"] == 25.5
