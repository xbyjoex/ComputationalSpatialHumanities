"""Regression guard for upsert_traffic_restrictions' stale-row sweep and its
volatile-key-aware dedup hash.

The live WFS source (geodienste.leipzig.de .../verkehrsraumeinschraenkungen)
exposes a stable id only as lowercase "objectid" — the old id/ID-only lookup
always came up empty, so every row fell back to the MD5(properties || geom)
hash. Every feature's properties also carry "fme_tstamp" (an FME export
timestamp that changes daily), which flipped that hash daily even for
unchanged restrictions, duplicating the ~1.5k-feature snapshot once per day
(63,866 rows in prod vs. ~1,482 in the current feed). This mirrors
test_geo_features_sweep.py's fake-cursor approach: assert on the SQL/params
issued rather than against a real database (none is available locally).
"""

from __future__ import annotations

import json

from src.loaders.postgres import upsert_traffic_restrictions

FEATURE_WITH_ID = {
    "type": "Feature",
    "properties": {"id": "1", "fme_tstamp": "2026-07-07T02:00:00Z"},
    "geometry": {"type": "Point", "coordinates": [12.37, 51.34]},
}

FEATURE_WITH_OBJECTID = {
    "type": "Feature",
    "properties": {"objectid": "42", "fme_tstamp": "2026-07-07T02:00:00Z"},
    "geometry": {"type": "Point", "coordinates": [12.37, 51.34]},
}

FEATURE_NO_STABLE_ID = {
    "type": "Feature",
    "properties": {"bezeichnung": "Baustelle Ring", "fme_tstamp": "2026-07-07T02:00:00Z"},
    "geometry": {"type": "Point", "coordinates": [12.37, 51.34]},
}

INSERT_SQL_FRAGMENT = "INSERT INTO core.traffic_restrictions"
SWEEP_SQL_FRAGMENT = "DELETE FROM core.traffic_restrictions"


class FakeCursor:
    def __init__(self, rowcount: int = 0):
        self.executed: list[tuple[str, tuple]] = []
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, rowcount: int = 0):
        self._cursor = FakeCursor(rowcount=rowcount)
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True


def _sweep_calls(cur: FakeCursor) -> list[tuple[str, tuple]]:
    return [(sql, params) for sql, params in cur.executed if SWEEP_SQL_FRAGMENT in sql]


def _insert_calls(cur: FakeCursor) -> list[tuple[str, tuple]]:
    return [(sql, params) for sql, params in cur.executed if INSERT_SQL_FRAGMENT in sql]


def test_sweep_deletes_stale_rows_when_enabled_and_rows_loaded():
    conn = FakeConnection(rowcount=17)
    loaded = upsert_traffic_restrictions(
        conn, "ds-1", [FEATURE_WITH_ID], restriction_type="point", sweep_stale=True
    )

    assert loaded == 1
    sweeps = _sweep_calls(conn._cursor)
    assert len(sweeps) == 1
    sql, params = sweeps[0]
    assert "dataset_id = %s" in sql
    assert "updated_at < NOW()" in sql
    assert params == ("ds-1",)
    # Sweep must run before the commit that seals the transaction.
    assert conn.committed is True


def test_sweep_not_issued_when_disabled():
    conn = FakeConnection()
    upsert_traffic_restrictions(conn, "ds-1", [FEATURE_WITH_ID], restriction_type="point")

    assert _sweep_calls(conn._cursor) == []


def test_sweep_not_issued_when_nothing_loaded():
    # An empty/failed extraction must never wipe the dataset.
    conn = FakeConnection()
    loaded = upsert_traffic_restrictions(
        conn, "ds-1", [], restriction_type="point", sweep_stale=True
    )

    assert loaded == 0
    assert _sweep_calls(conn._cursor) == []


def test_sweep_default_is_off():
    conn = FakeConnection()
    upsert_traffic_restrictions(conn, "ds-1", [FEATURE_WITH_ID], restriction_type="point")

    assert _sweep_calls(conn._cursor) == []


def test_objectid_used_as_stable_id_when_id_missing():
    conn = FakeConnection()
    upsert_traffic_restrictions(conn, "ds-1", [FEATURE_WITH_OBJECTID], restriction_type="point")

    sql, params = _insert_calls(conn._cursor)[0]
    restriction_id, dedup_nullif_arg = params[0], params[9]
    assert restriction_id == "42"
    assert dedup_nullif_arg == "42"


def test_fme_tstamp_excluded_from_hash_params_but_kept_in_properties():
    conn = FakeConnection()
    upsert_traffic_restrictions(conn, "ds-1", [FEATURE_NO_STABLE_ID], restriction_type="point")

    sql, params = _insert_calls(conn._cursor)[0]
    properties_col_arg, dedup_nullif_arg, hash_props_arg = params[8], params[9], params[10]

    # No stable id on this feature -> falls back to the MD5(properties||geom) hash.
    assert dedup_nullif_arg == ""

    # properties column keeps the timestamp verbatim...
    assert "fme_tstamp" in properties_col_arg
    assert json.loads(properties_col_arg)["fme_tstamp"] == "2026-07-07T02:00:00Z"

    # ...but the hash input used for the fallback dedup_key excludes it, so a
    # day-to-day fme_tstamp change alone can't flip the dedup_key.
    assert "fme_tstamp" not in hash_props_arg
    assert json.loads(hash_props_arg) == {"bezeichnung": "Baustelle Ring"}


def test_fme_tstamp_change_alone_does_not_change_hash_input():
    conn = FakeConnection()
    day1 = {**FEATURE_NO_STABLE_ID, "properties": {**FEATURE_NO_STABLE_ID["properties"], "fme_tstamp": "2026-07-06T02:00:00Z"}}
    day2 = {**FEATURE_NO_STABLE_ID, "properties": {**FEATURE_NO_STABLE_ID["properties"], "fme_tstamp": "2026-07-07T02:00:00Z"}}

    upsert_traffic_restrictions(conn, "ds-1", [day1], restriction_type="point")
    upsert_traffic_restrictions(conn, "ds-1", [day2], restriction_type="point")

    inserts = _insert_calls(conn._cursor)
    assert len(inserts) == 2
    hash_arg_day1 = inserts[0][1][10]
    hash_arg_day2 = inserts[1][1][10]
    assert hash_arg_day1 == hash_arg_day2
