"""Regression guard for the stale-row sweep in upsert_geo_features.

Some WFS/GeoJSON sources (e.g. Baumkataster) hand out new volatile feature
ids on every fetch, so the ON CONFLICT (dataset_id, dedup_key) upsert below
never matches and every run re-inserted the full snapshot — 7M duplicate
rows / 12 GB in core.geo_features in production. sweep_stale=True deletes,
in the same transaction, whatever this run did not touch (updated_at < NOW()
inside a transaction where every touched row shares this run's NOW()).

No local Postgres is available, so this exercises the loader against a fake
cursor/connection and asserts on the SQL/params it issues rather than
against a real database.
"""

from __future__ import annotations

from src.loaders.postgres import upsert_geo_features

FEATURE = {
    "type": "Feature",
    "properties": {"id": "1"},
    "geometry": {"type": "Point", "coordinates": [12.37, 51.34]},
}

SWEEP_SQL_FRAGMENT = "DELETE FROM core.geo_features"


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


def test_sweep_deletes_stale_rows_when_enabled_and_rows_loaded():
    conn = FakeConnection(rowcount=42)
    loaded = upsert_geo_features(
        conn, "ds-1", [FEATURE], feature_type="tree", sweep_stale=True
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
    upsert_geo_features(conn, "ds-1", [FEATURE], feature_type="tree", sweep_stale=False)

    assert _sweep_calls(conn._cursor) == []


def test_sweep_not_issued_when_nothing_loaded():
    # An empty/failed extraction must never wipe the dataset.
    conn = FakeConnection()
    loaded = upsert_geo_features(conn, "ds-1", [], feature_type="tree", sweep_stale=True)

    assert loaded == 0
    assert _sweep_calls(conn._cursor) == []


def test_sweep_default_is_off():
    conn = FakeConnection()
    upsert_geo_features(conn, "ds-1", [FEATURE], feature_type="tree")

    assert _sweep_calls(conn._cursor) == []
