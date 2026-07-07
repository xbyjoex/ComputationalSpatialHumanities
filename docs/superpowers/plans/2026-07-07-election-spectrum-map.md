# Politisches-Spektrum-Karte (Wahlergebnisse) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wahlergebnisse als Links-Rechts-Choropleth (rot=links, blau=rechts, Bundestags-Sitzordnung) mit Hover-Pie-Chart, funktionierend über alle Wahl-Datensätze (5 moderne Wahlen + kleinräumige Historie 1994–2025).

**Architecture:** Kuratiertes Partei-Register (`party_registry.json`) → `core.parties`/`core.party_aliases`; MatView `mart.election_party_shares` vereinheitlicht `core.election_results` und die kleinräumigen `core.statistics`-Reihen; `GET /elections/spectrum` liefert GeoJSON mit Score + kompletter Parteiverteilung pro Gebiet; Frontend rendert divergierende Farbskala + Hover-Tooltip mit Recharts-Pie. Schritt 0 ist der 304-Skip-Fix, der `core.election_results` überhaupt erst füllt.

**Tech Stack:** PostgreSQL 16 + PostGIS, psycopg3 (`dict_row`), FastAPI, React 18 + TypeScript + Zustand + react-query v3 (`useQuery(key, fn, opts)`) + MapLibre (`@vis.gl/react-maplibre`) + Recharts + Tailwind.

**Spec:** `docs/superpowers/specs/2026-07-07-election-spectrum-map-design.md`

## Global Constraints

- **Kein Docker/DB auf diesem Mac** (nur Docker-CLI ohne Daemon): DB-abhängige Verifikation NUR auf dem VPS (`ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech`, psql via `docker exec -i leipzig-data-db-1 psql -U leipzig -d leipzig_data`). Lokal: pytest (reine Funktionen), Import-Smoke, `npm run lint`/`build`.
- **Python 3.11+**, beide Pakete editable (`pip install -e .`); pytest ist nicht in den Dependencies — bei Bedarf `pip install pytest` im venv.
- ETL **und** Backend nutzen psycopg3 mit `row_factory=dict_row` — Zeilen sind dicts, nie Tupel-Indexe verwenden.
- Migrationen liegen in `sql/migrations/`, werden vom ETL-Scheduler beim Start auto-appliziert (`etl/src/db.py:run_migrations()`), Tracking in `public.schema_migrations`. Nächste freie Nummer: **016**.
- **Push auf `main` löst das Deploy aus** (GitHub Actions → VPS). Lokal committen ist safe; `git push` erst im Rollout-Task und nur nach Rückfrage beim User.
- UI-Texte auf Deutsch, im Stil der bestehenden HUD-Labels.
- Commit-Messages enden mit `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Der Score-Wertebereich der Farbskala ist die Konstante `SPECTRUM_DOMAIN = 0.5` (nur im Frontend, `frontend/src/api/elections.ts`).
- Sonstige-Farbe überall: `#6b7683`.

---

### Task 1: ETL 304-Skip-Guard für Elections-Datensätze

`core.election_results` ist leer, weil `run_dataset` bei gespeichertem ETag mit 304/„unchanged“ überspringt, obwohl die Zieltabelle nie befüllt wurde. Elections-Datensätze dürfen den Skip nur nehmen, wenn ihre Daten schon da sind.

**Files:**
- Modify: `etl/src/pipeline.py:86-115` (Change-Detection-Block in `run_dataset`)

**Interfaces:**
- Consumes: `elections.route_for(dataset_id)` (bereits importiert via `from .domains import elections`), `get_conn()` (dict_row).
- Produces: keine neuen Symbole; Verhaltensänderung im Skip-Pfad.

- [ ] **Step 1: Guard implementieren**

In `etl/src/pipeline.py` den Block ab `# ── Change detection via HEAD` so ändern (nach dem Laden von `stored`, vor dem `try`):

```python
    # ── Change detection via HEAD (no body download) ─────────────────────────
    with get_conn() as conn:
        stored = get_dataset_checksum(conn, dataset_id)

    # Elections-Datensätze: 304/ETag-Skip nur, wenn die Zieltabelle für diesen
    # Datensatz auch Zeilen hat. Sonst bleibt core.election_results nach einem
    # Checksum-Eintrag aus der Vor-Elections-Ära für immer leer (Skip-Schleife).
    force_reload = False
    if elections.route_for(dataset_id):
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM core.election_results WHERE dataset_id = %s) AS has_rows",
                    (dataset_id,),
                )
                force_reload = not cur.fetchone()["has_rows"]
        if force_reload:
            logger.info("[FORCE] %-60s election target empty — bypassing 304 skip", title[:60])
```

Dann die beiden Skip-Bedingungen erweitern:

```python
        if probe.status_code == 304 and not force_reload:
```

und

```python
        if new_etag and new_etag == stored_etag and not force_reload:
```

- [ ] **Step 2: Import-Smoke lokal**

Run: `cd etl && python -c "import ast; ast.parse(open('src/pipeline.py').read()); print('OK')"`
Expected: `OK` (kein venv nötig; reine Syntaxprüfung. Falls ein venv mit Dependencies existiert: `python -c "from src import pipeline; print('OK')"`)

- [ ] **Step 3: Commit**

```bash
git add etl/src/pipeline.py
git commit -m "Fix ETL skip loop: never 304-skip election datasets with empty target

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Partei-Register + kleinräumig-Quellen (Configs)

**Files:**
- Create: `party_registry.json` (Repo-Root)
- Modify: `election_definitions.json` (neuer Top-Level-Key `kleinraeumig_sources`)
- Modify: `etl/src/config.py:53-56` (neues `parties_path` nach `elections_path`)
- Modify: `infrastructure/docker-compose.yml:88` (Volume-Mount)

**Interfaces:**
- Produces: `party_registry.json` mit Schema `{"parties": [{"key", "name", "position", "color", "aliases"}]}`; `settings.parties_path`; `election_definitions.json["kleinraeumig_sources"]: {dataset_id: election_type}`.

- [ ] **Step 1: `party_registry.json` anlegen** (vollständiger Inhalt)

```json
{
  "comment": "Kuratiertes Partei-Register. position = Links-Rechts nach Bundestags-Sitzordnung (21. BT: Linke, Grüne, SPD, Union, AfD; FDP bis 2025 zwischen SPD/Grünen und Union; BSW saß im 20. BT als Gruppe neben der Linken). Parteien ohne Eintrag werden als 'Sonstige' aggregiert und fließen nicht in den Score ein. Matching: lower(trim(alias)).",
  "parties": [
    {
      "key": "linke",
      "name": "Die Linke",
      "position": -1.0,
      "color": "#c45ab3",
      "aliases": ["DIE LINKE", "DIe Linke", "Die Linke", "LINKE", "Linke", "PDS", "Die Linke.PDS", "DIE LINKE."]
    },
    {
      "key": "bsw",
      "name": "BSW",
      "position": -0.75,
      "color": "#9d8cff",
      "aliases": ["BSW", "Bündnis Sahra Wagenknecht"]
    },
    {
      "key": "gruene",
      "name": "Grüne",
      "position": -0.45,
      "color": "#3dd68c",
      "aliases": ["GRÜNE", "Grüne", "GRUENE", "BÜNDNIS 90/DIE GRÜNEN", "Bündnis 90/Die Grünen", "B90/Grüne"]
    },
    {
      "key": "spd",
      "name": "SPD",
      "position": -0.25,
      "color": "#ff6e5e",
      "aliases": ["SPD"]
    },
    {
      "key": "fdp",
      "name": "FDP",
      "position": 0.25,
      "color": "#e8d553",
      "aliases": ["FDP", "F.D.P."]
    },
    {
      "key": "cdu",
      "name": "CDU",
      "position": 0.6,
      "color": "#5d7a8d",
      "aliases": ["CDU"]
    },
    {
      "key": "afd",
      "name": "AfD",
      "position": 1.0,
      "color": "#53b9e8",
      "aliases": ["AfD", "AFD"]
    }
  ]
}
```

- [ ] **Step 2: `kleinraeumig_sources` in `election_definitions.json`**

Nach dem `"elections": [...]`-Array (als zweiter Top-Level-Key, vor der schließenden Klammer) einfügen:

```json
  "kleinraeumig_sources": {
    "cbd82a0a-a6e7-45c4-a69a-00e69552fbb4": "bundestagswahl",
    "1da7d611-5f59-41b6-b62c-5032f9883acf": "europawahl",
    "2b2f9e42-4c85-470d-a9f3-7e163d23ddb7": "landtagswahl",
    "dd2024f3-7095-43a2-8817-1ebf9dbbe6a8": "stadtratswahl",
    "8540fb95-9df3-4c2d-aacc-00ee1510d136": "oberbuergermeisterwahl"
  }
```

- [ ] **Step 3: `parties_path` in `etl/src/config.py`** — nach dem `elections_path`-Block:

```python
    parties_path: Path = Path(
        os.getenv("ETL_PARTIES_PATH")
        or Path(__file__).parent.parent / "party_registry.json"
    )
```

- [ ] **Step 4: Volume-Mount in `infrastructure/docker-compose.yml`** — im `etl`-Service nach der `election_definitions.json`-Zeile:

```yaml
      - ./party_registry.json:/app/party_registry.json:ro
```

- [ ] **Step 5: JSON-Validität prüfen**

Run: `python3 -c "import json; json.load(open('party_registry.json')); json.load(open('election_definitions.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add party_registry.json election_definitions.json etl/src/config.py infrastructure/docker-compose.yml
git commit -m "Add curated party registry (Bundestag seating) + kleinraeumig source map

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Migration 016 — Tabellen + MatView + refresh_all

**Files:**
- Create: `sql/migrations/016_election_spectrum.sql`

**Interfaces:**
- Produces: `core.parties(key, name, position, color, aliases)`, `core.party_aliases(alias_norm, party_key)`, `core.election_sources(dataset_id, election_type, kind)`, `mart.election_party_shares(election_type, year, level, spatial_code, gebiet_name, raw_party, party_key, party_name, party_position, party_color, share_pct, votes, turnout_pct, source)`; `mart.refresh_all()` refresht die neue View mit.

- [ ] **Step 1: Migration schreiben** (vollständiger Dateiinhalt)

```sql
-- =============================================================================
-- Migration 016: Partei-Register + vereinheitlichte Wahl-Anteile (Spektrum-Karte)
-- =============================================================================

-- ── Kuratiertes Partei-Register (sync aus party_registry.json) ───────────────
CREATE TABLE IF NOT EXISTS core.parties (
    key       TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    position  REAL,              -- Links-Rechts (Sitzordnung); NULL = ohne Score
    color     TEXT NOT NULL,
    aliases   TEXT[] NOT NULL DEFAULT '{}'
);

-- Normalisierter Alias-Lookup für SQL-Joins (lower(trim(alias)) → key)
CREATE TABLE IF NOT EXISTS core.party_aliases (
    alias_norm TEXT PRIMARY KEY,
    party_key  TEXT NOT NULL REFERENCES core.parties(key) ON DELETE CASCADE
);

-- kleinräumig-Statistik-Datensatz → Wahltyp (sync aus election_definitions.json)
CREATE TABLE IF NOT EXISTS core.election_sources (
    dataset_id    TEXT PRIMARY KEY REFERENCES core.datasets(id),
    election_type TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'kleinraeumig'
);

-- ── Vereinheitlichte Parteianteile über beide Quellen ────────────────────────
-- Quelle A: core.election_results (exakte Stimmen, moderne Wahlen).
-- Quelle B: core.statistics kleinräumig ('Stimmenanteile X'), nur für
--           (Wahltyp, Jahr, Ebene)-Kombinationen, die A nicht liefert.
-- GROUP BY je Quelle: mehrere gebiet_codes können auf denselben spatial_code
-- auflösen (Namens-Aliase) — Stimmen werden summiert, Anteile neu berechnet.
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.election_party_shares AS
WITH results_src AS (
    SELECT e.election_type,
           e.year,
           r.level,
           r.spatial_code,
           min(r.gebiet_name)  AS gebiet_name,
           r.party             AS raw_party,
           sum(r.zweitstimmen)::numeric * 100 / NULLIF(sum(r.gueltige_zweit), 0) AS share_pct,
           sum(r.zweitstimmen) AS votes,
           sum(r.waehler)::numeric * 100 / NULLIF(sum(r.wahlberechtigte), 0)     AS turnout_pct,
           'results'::text     AS source
    FROM core.election_results r
    JOIN core.elections e ON e.election_id = r.election_id
    WHERE r.spatial_code IS NOT NULL
      AND r.zweitstimmen IS NOT NULL
    GROUP BY e.election_type, e.year, r.level, r.spatial_code, r.party
),
turnout_b AS (
    SELECT dataset_id, spatial_code, period_year,
           avg(metric_value) AS turnout_pct
    FROM core.statistics
    WHERE metric_name = 'Wahlbeteiligung' AND spatial_code IS NOT NULL
    GROUP BY dataset_id, spatial_code, period_year
),
statistik_src AS (
    SELECT es.election_type,
           s.period_year          AS year,
           s.spatial_unit         AS level,
           s.spatial_code,
           min(s.spatial_key)     AS gebiet_name,
           substring(s.metric_name FROM 16) AS raw_party,   -- 'Stimmenanteile ' abschneiden
           avg(s.metric_value)    AS share_pct,
           NULL::bigint           AS votes,
           min(t.turnout_pct)     AS turnout_pct,
           'statistik'::text      AS source
    FROM core.statistics s
    JOIN core.election_sources es ON es.dataset_id = s.dataset_id
    LEFT JOIN turnout_b t
        ON t.dataset_id = s.dataset_id
       AND t.spatial_code = s.spatial_code
       AND t.period_year = s.period_year
    WHERE s.metric_name LIKE 'Stimmenanteile %'
      AND s.spatial_code IS NOT NULL
      AND s.period_year IS NOT NULL
      AND s.metric_value IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM core.election_results r2
          JOIN core.elections e2 ON e2.election_id = r2.election_id
          WHERE e2.election_type = es.election_type
            AND e2.year          = s.period_year
            AND r2.level         = s.spatial_unit
            AND r2.spatial_code IS NOT NULL
      )
    GROUP BY es.election_type, s.period_year, s.spatial_unit, s.spatial_code,
             substring(s.metric_name FROM 16)
),
unified AS (
    SELECT * FROM results_src
    UNION ALL
    SELECT * FROM statistik_src
)
SELECT u.election_type,
       u.year,
       u.level,
       u.spatial_code,
       u.gebiet_name,
       u.raw_party,
       p.key                          AS party_key,
       COALESCE(p.name, u.raw_party)  AS party_name,
       p.position                     AS party_position,
       p.color                        AS party_color,
       u.share_pct,
       u.votes,
       u.turnout_pct,
       u.source
FROM unified u
LEFT JOIN core.party_aliases pa ON pa.alias_norm = lower(trim(u.raw_party))
LEFT JOIN core.parties p        ON p.key = pa.party_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_eps_unique
    ON mart.election_party_shares(election_type, year, level, spatial_code, raw_party);
CREATE INDEX IF NOT EXISTS idx_mart_eps_lookup
    ON mart.election_party_shares(election_type, year, level);

-- ── refresh_all um die neue View erweitern ────────────────────────────────────
CREATE OR REPLACE FUNCTION mart.refresh_all()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.park_ride_latest;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.bicycle_daily;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.active_restrictions;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.statistics_latest;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.geo_features_map;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart.election_party_shares;
    REFRESH MATERIALIZED VIEW mart.dataset_status;
END;
$$ LANGUAGE plpgsql;
```

**Achtung:** `mart.refresh_all()` hier exakt aus dem aktuellen Stand von `sql/migrations/002_materialized_views.sql:126-136` übernehmen + die eine neue Zeile — nicht blind kopieren, falls eine spätere Migration die Funktion schon einmal ersetzt hat (prüfen: `grep -rn "refresh_all" sql/migrations/`).

- [ ] **Step 2: SQL-Syntax-Smoke (ohne DB)**

Run: `python3 -c "sql = open('sql/migrations/016_election_spectrum.sql').read(); assert sql.count('CREATE') >= 5; print('OK', len(sql), 'bytes')"`
Expected: `OK … bytes` (echte Ausführung erst auf dem VPS durch den Scheduler; Task 12 verifiziert.)

- [ ] **Step 3: Commit**

```bash
git add sql/migrations/016_election_spectrum.sql
git commit -m "Add migration 016: party registry tables + unified election shares mart

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: ETL-Sync (Parteien, kleinräumig-Quellen) + Scheduler-Wiring

**Files:**
- Modify: `etl/src/domains/elections.py` (neu: `load_party_registry()`, `sync_parties()`; erweitert: `sync_elections()`)
- Modify: `etl/src/scheduler.py:253-259` (Sync-Aufrufe + MatView-Startup-Refresh)

**Interfaces:**
- Consumes: `settings.parties_path` (Task 2), Tabellen aus Migration 016 (Task 3).
- Produces: `elections.load_party_registry() -> dict`, `elections.sync_parties(conn, config) -> int` (Anzahl Parteien); `sync_elections` schreibt zusätzlich `core.election_sources`.

- [ ] **Step 1: `load_party_registry` + `sync_parties` in `etl/src/domains/elections.py`** (ans Dateiende anfügen)

```python
def load_party_registry() -> dict[str, Any]:
    """party_registry.json (kuratiert): Parteien mit Sitzordnungs-Position."""
    path = Path(settings.parties_path)
    if not path.exists():
        repo_root = Path(__file__).resolve().parents[3] / "party_registry.json"
        path = repo_root if repo_root.exists() else path
    if not path.exists():
        logger.warning("No party_registry.json found — party sync disabled")
        return {"parties": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sync_parties(conn: psycopg.Connection, config: dict[str, Any]) -> int:
    """Sync party_registry.json → core.parties + core.party_aliases."""
    parties = config.get("parties", [])
    keys = [p["key"] for p in parties]
    with conn.cursor() as cur:
        for p in parties:
            cur.execute(
                """
                INSERT INTO core.parties (key, name, position, color, aliases)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    name     = EXCLUDED.name,
                    position = EXCLUDED.position,
                    color    = EXCLUDED.color,
                    aliases  = EXCLUDED.aliases
                """,
                (p["key"], p["name"], p.get("position"), p["color"],
                 p.get("aliases", [])),
            )
        cur.execute("DELETE FROM core.parties WHERE key <> ALL(%s)", (keys or [""],))
        # Alias-Lookup komplett neu aufbauen (klein, deterministisch)
        cur.execute("DELETE FROM core.party_aliases")
        for p in parties:
            for alias in {p["name"], *p.get("aliases", [])}:
                cur.execute(
                    """
                    INSERT INTO core.party_aliases (alias_norm, party_key)
                    VALUES (lower(trim(%s)), %s)
                    ON CONFLICT (alias_norm) DO NOTHING
                    """,
                    (alias, p["key"]),
                )
        conn.commit()
    return len(parties)
```

- [ ] **Step 2: `sync_elections` erweitern** — in `etl/src/domains/elections.py`, innerhalb `sync_elections` nach der Eltern-`for e in elections`-Schleife, vor dem `if dataset_ids:`-Block:

```python
        # kleinräumig-Statistik-Datensätze → Wahltyp (für mart.election_party_shares)
        sources = config.get("kleinraeumig_sources", {})
        cur.execute(
            "DELETE FROM core.election_sources WHERE dataset_id <> ALL(%s)",
            (list(sources) or [""],),
        )
        for ds_id, etype in sources.items():
            cur.execute(
                """
                INSERT INTO core.election_sources (dataset_id, election_type, kind)
                VALUES (%s, %s, 'kleinraeumig')
                ON CONFLICT (dataset_id) DO UPDATE SET
                    election_type = EXCLUDED.election_type
                """,
                (ds_id, etype),
            )
```

- [ ] **Step 3: Scheduler-Wiring** — in `etl/src/scheduler.py`, direkt nach dem bestehenden „Election domain registry“-try/except-Block (nach Zeile ~259):

```python
    # Partei-Register (party_registry.json → core.parties/party_aliases)
    try:
        with get_conn() as conn:
            n_parties = elections.sync_parties(conn, elections.load_party_registry())
            logger.info("Parties synced: %d", n_parties)
    except Exception as exc:
        logger.error("Party sync failed: %s", exc)

    # Spektrum-View einmal beim Start füllen (sonst erst nach dem Nightly)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("REFRESH MATERIALIZED VIEW mart.election_party_shares")
                conn.commit()
    except Exception as exc:
        logger.warning("election_party_shares startup refresh failed: %s", exc)
```

- [ ] **Step 4: Syntax-Smoke**

Run: `cd etl && python -c "import ast; [ast.parse(open(f).read()) for f in ('src/domains/elections.py','src/scheduler.py')]; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add etl/src/domains/elections.py etl/src/scheduler.py
git commit -m "Sync party registry and kleinraeumig election sources on scheduler startup

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Backend `compute_spectrum` (TDD)

**Files:**
- Create: `backend/src/api/spectrum.py`
- Test: `backend/tests/test_spectrum.py` (Verzeichnis neu; leere `backend/tests/__init__.py` ist NICHT nötig — pytest rootdir reicht)

**Interfaces:**
- Produces: `compute_spectrum(rows: list[dict]) -> dict` — Input-Zeilen `{key, name, position, color, share}` (eine pro Partei eines Gebiets; `position`/`share` können `None`/`Decimal` sein), Output `{"score": float|None, "coverage_pct": float, "parties": [{"key", "name", "share", "color"}]}`; Konstante `SONSTIGE_COLOR = "#6b7683"`. Wird von Task 6 konsumiert.

- [ ] **Step 1: Failing Tests schreiben** — `backend/tests/test_spectrum.py`:

```python
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
```

- [ ] **Step 2: Tests laufen lassen — müssen fehlschlagen**

Run: `cd backend && python -m pytest tests/test_spectrum.py -v` (vorher einmalig: `pip install pytest` im venv)
Expected: FAIL — `ModuleNotFoundError: No module named 'src.api.spectrum'`

- [ ] **Step 3: Implementierung** — `backend/src/api/spectrum.py`:

```python
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
```

- [ ] **Step 4: Tests laufen lassen — müssen bestehen**

Run: `cd backend && python -m pytest tests/test_spectrum.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/api/spectrum.py backend/tests/test_spectrum.py
git commit -m "Add compute_spectrum: seat-position weighted left-right score

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Backend-Endpoints `/elections/spectrum` + `/options`, Summary-Farben

**Files:**
- Modify: `backend/src/api/routers/elections_router.py`

**Interfaces:**
- Consumes: `compute_spectrum`, `SONSTIGE_COLOR` aus `..spectrum` (Task 5); `mart.election_party_shares`, `core.parties`, `core.party_aliases` (Task 3/4).
- Produces:
  - `GET /elections/spectrum?election_type&year&level` → `{"type": "FeatureCollection", "features": [{geometry, properties: {gebiet_code, name, score, coverage_pct, turnout_pct, parties: [{key,name,share,color}]}}]}`
  - `GET /elections/spectrum/options` → `{"elections": [{"election_type","title","years":[{"year","levels":[…]}]}], "parties": [{"key","name","position","color"}]}`
  - `GET /elections/{id}/summary`: Partei-Einträge zusätzlich mit `party_color: string|null`.

- [ ] **Step 1: Import ergänzen** — oben in `elections_router.py`:

```python
from ..spectrum import compute_spectrum
```

- [ ] **Step 2: Spectrum-Endpoints einfügen** — direkt nach `list_elections` (vor `election_summary`, damit statische Routen vor den `{election_id}`-Routen stehen):

```python
_SPECTRUM_LEVELS = ("wahlbezirk", "ortsteil", "stadtbezirk")
_SPECTRUM_TITLES = {
    "bundestagswahl": "Bundestagswahl",
    "europawahl": "Europawahl",
    "landtagswahl": "Landtagswahl",
    "stadtratswahl": "Stadtratswahl",
    "oberbuergermeisterwahl": "Oberbürgermeisterwahl",
}


@router.get("/spectrum/options")
@cached(ttl=3600)
async def spectrum_options(_user: CurrentUser) -> ORJSONResponse:
    """Verfügbare (Wahltyp, Jahr, Ebene)-Kombinationen + Partei-Register."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT election_type, year,
                       array_agg(DISTINCT level ORDER BY level) AS levels
                FROM mart.election_party_shares
                GROUP BY election_type, year
                ORDER BY election_type, year DESC
                """
            )
            combos = await cur.fetchall()
            await cur.execute(
                """
                SELECT key, name, position, color
                FROM core.parties
                ORDER BY position NULLS LAST, key
                """
            )
            parties = await cur.fetchall()

    grouped: dict[str, list[dict]] = {}
    for c in combos:
        grouped.setdefault(c["election_type"], []).append(
            {"year": c["year"], "levels": c["levels"]}
        )
    elections = [
        {"election_type": t, "title": _SPECTRUM_TITLES.get(t, t.title()), "years": years}
        for t, years in grouped.items()
    ]
    return ORJSONResponse({"elections": elections, "parties": parties})


@router.get("/spectrum")
@cached(ttl=3600)
async def election_spectrum(
    _user: CurrentUser,
    election_type: str = Query(..., max_length=50),
    year: int = Query(...),
    level: str = Query("ortsteil"),
) -> ORJSONResponse:
    """Links-Rechts-Score + Parteiverteilung je Gebiet als GeoJSON.

    Ein Fetch versorgt Kartenfarbe UND Hover-Pies (parties in den Properties).
    Wahlbezirk-Geometrien sind je Wahljahr versioniert (boundary_year).
    """
    if level not in _SPECTRUM_LEVELS:
        raise HTTPException(status_code=400, detail=f"level muss eines von {_SPECTRUM_LEVELS} sein")
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT eps.spatial_code,
                       COALESCE(b.name, min(eps.gebiet_name)) AS name,
                       max(eps.turnout_pct)                   AS turnout_pct,
                       ST_AsGeoJSON(b.geom)::jsonb            AS geometry,
                       jsonb_agg(jsonb_build_object(
                           'key',      eps.party_key,
                           'name',     eps.party_name,
                           'position', eps.party_position,
                           'color',    eps.party_color,
                           'share',    eps.share_pct
                       )) AS shares
                FROM mart.election_party_shares eps
                JOIN core.admin_boundaries b
                    ON b.boundary_type = eps.level
                    AND b.code = eps.spatial_code
                    AND (b.boundary_year = 0 OR b.boundary_year = eps.year)
                WHERE eps.election_type = %s AND eps.year = %s AND eps.level = %s
                GROUP BY eps.spatial_code, b.name, b.geom
                """,
                (election_type, year, level),
            )
            rows = await cur.fetchall()

    features = []
    for r in rows:
        spec = compute_spectrum(r["shares"])
        features.append(
            {
                "type": "Feature",
                "geometry": r["geometry"],
                "properties": {
                    "gebiet_code": r["spatial_code"],
                    "name": r["name"],
                    "score": spec["score"],
                    "coverage_pct": spec["coverage_pct"],
                    "turnout_pct": float(r["turnout_pct"]) if r["turnout_pct"] is not None else None,
                    "parties": spec["parties"],
                },
            }
        )
    return ORJSONResponse({"type": "FeatureCollection", "features": features})
```

- [ ] **Step 3: Summary-Endpoint um Parteifarbe erweitern** — in `election_summary` die Partei-Query ersetzen durch:

```python
            await cur.execute(
                """
                SELECT r.party, r.party_index, r.erststimmen, r.zweitstimmen,
                       ROUND(r.zweitstimmen::numeric * 100 / NULLIF(r.gueltige_zweit, 0), 2) AS anteil_pct,
                       r.wahlberechtigte, r.waehler, r.briefwaehler, r.gueltige_zweit,
                       p.color AS party_color
                FROM core.election_results r
                LEFT JOIN core.party_aliases pa ON pa.alias_norm = lower(trim(r.party))
                LEFT JOIN core.parties p ON p.key = pa.party_key
                WHERE r.election_id = %s AND r.level = 'stadt'
                ORDER BY r.zweitstimmen DESC NULLS LAST
                """,
                (election_id,),
            )
```

(Das Ausfiltern der Zählfelder weiter unten in der Funktion lässt `party_color` automatisch durch — Exclusion-Set unverändert.)

- [ ] **Step 4: Syntax-Smoke**

Run: `cd backend && python -c "import ast; ast.parse(open('src/api/routers/elections_router.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/src/api/routers/elections_router.py
git commit -m "Add /elections/spectrum + /options endpoints, party colors in summary

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Frontend API-Layer + mapStore

**Files:**
- Create: `frontend/src/api/elections.ts`
- Modify: `frontend/src/store/mapStore.ts`

**Interfaces:**
- Produces (von Task 8–10 konsumiert):
  - `SPECTRUM_DOMAIN = 0.5`, `SONSTIGE_COLOR = "#6b7683"`
  - Typen `SpectrumPartyShare {key: string|null; name: string; share: number; color: string}`, `SpectrumFeatureProps {gebiet_code, name, score: number|null, coverage_pct: number, turnout_pct: number|null, parties: SpectrumPartyShare[]}`, `SpectrumOptions {elections: {election_type, title, years: {year, levels: string[]}[]}[], parties: {key,name,position: number|null,color}[]}`
  - `fetchSpectrumOptions(): Promise<SpectrumOptions>`, `fetchSpectrum(election_type, year, level)`
  - mapStore: `LayerKey` um `"elections"` erweitert; `ElectionSelection {electionType: string; year: number; level: string}`; `electionSelection: ElectionSelection | null`; `setElectionSelection(sel)`.

- [ ] **Step 1: `frontend/src/api/elections.ts` anlegen**

```ts
import { apiClient } from "./client";

/** Symmetrischer Score-Wertebereich der Farbskala (Werte werden geclampt). */
export const SPECTRUM_DOMAIN = 0.5;
export const SONSTIGE_COLOR = "#6b7683";

export interface SpectrumPartyShare {
  key: string | null;
  name: string;
  share: number;
  color: string;
}

export interface SpectrumFeatureProps {
  gebiet_code: string;
  name: string;
  score: number | null;
  coverage_pct: number;
  turnout_pct: number | null;
  parties: SpectrumPartyShare[];
}

export interface SpectrumYear {
  year: number;
  levels: string[];
}

export interface SpectrumElection {
  election_type: string;
  title: string;
  years: SpectrumYear[];
}

export interface SpectrumOptions {
  elections: SpectrumElection[];
  parties: { key: string; name: string; position: number | null; color: string }[];
}

export const fetchSpectrumOptions = (): Promise<SpectrumOptions> =>
  apiClient.get("/elections/spectrum/options").then((r) => r.data);

export const fetchSpectrum = (election_type: string, year: number, level: string) =>
  apiClient
    .get("/elections/spectrum", { params: { election_type, year, level } })
    .then((r) => r.data);
```

- [ ] **Step 2: mapStore erweitern** — `frontend/src/store/mapStore.ts`:

Zeile 3 ersetzen:

```ts
export type LayerKey = "geo_features" | "park_ride" | "bicycle" | "restrictions" | "choropleth" | "elections";
```

Nach dem `DockItem`-Interface:

```ts
/** Aktive Wahl-Auswahl für die Politisches-Spektrum-Ebene. */
export interface ElectionSelection {
  electionType: string;
  year: number;
  level: string;
}
```

Im `MapState`-Interface (nach `spatialUnit: string;`):

```ts
  electionSelection: ElectionSelection | null;
```

und bei den Settern (nach `setSpatialUnit`):

```ts
  setElectionSelection: (sel: ElectionSelection | null) => void;
```

Im Store-Initializer (nach `spatialUnit: "ortsteil",`):

```ts
  electionSelection: null,
```

und bei den Setter-Implementierungen (nach `setSpatialUnit: ...`):

```ts
  setElectionSelection: (sel) => set({ electionSelection: sel }),
```

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/elections.ts frontend/src/store/mapStore.ts
git commit -m "Add spectrum API client + elections layer state

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: ElectionsControl im CatalogPanel

**Files:**
- Create: `frontend/src/components/ElectionsControl.tsx`
- Modify: `frontend/src/components/CatalogPanel.tsx` (Import + Render)

**Interfaces:**
- Consumes: `fetchSpectrumOptions`, Typen aus `../api/elections`; mapStore `elections`-Layer + `electionSelection` (Task 7).
- Produces: Default-Export `ElectionsControl` (ohne Props).

- [ ] **Step 1: `frontend/src/components/ElectionsControl.tsx` anlegen**

```tsx
import { useEffect } from "react";
import { useQuery } from "react-query";
import { Vote } from "lucide-react";
import clsx from "clsx";
import { fetchSpectrumOptions, SpectrumOptions } from "../api/elections";
import { useMapStore } from "../store/mapStore";

const LEVEL_LABELS: Record<string, string> = {
  ortsteil: "Ortsteil",
  stadtbezirk: "Stadtbezirk",
  wahlbezirk: "Wahlbezirk",
};

function pickLevel(levels: string[]): string {
  return levels.includes("ortsteil") ? "ortsteil" : levels[0];
}

/** Wahltyp/Jahr/Ebene-Picker für die Politisches-Spektrum-Ebene. */
export default function ElectionsControl() {
  const { activeLayers, setLayer, electionSelection, setElectionSelection } = useMapStore();
  const on = activeLayers.has("elections");

  const { data: options } = useQuery<SpectrumOptions>("spectrumOptions", fetchSpectrumOptions, {
    enabled: on,
    staleTime: 3_600_000,
  });

  // Default: jüngste Bundestagswahl, sobald Optionen da sind
  useEffect(() => {
    if (!on || electionSelection || !options?.elections.length) return;
    const el =
      options.elections.find((e) => e.election_type === "bundestagswahl") ?? options.elections[0];
    const y = el.years[0];
    setElectionSelection({ electionType: el.election_type, year: y.year, level: pickLevel(y.levels) });
  }, [on, options, electionSelection, setElectionSelection]);

  const current = options?.elections.find(
    (e) => e.election_type === electionSelection?.electionType
  );
  const currentYear = current?.years.find((y) => y.year === electionSelection?.year);

  return (
    <div className="mt-3 space-y-2 border-t border-gotham-700 pt-2.5">
      <button
        onClick={() => {
          setLayer("elections", !on);
          if (on) setElectionSelection(null);
        }}
        className="group flex w-full items-center gap-2 px-1 py-1 text-left transition-colors hover:bg-gotham-800/70"
      >
        <span
          className={clsx(
            "flex h-3 w-3 shrink-0 items-center justify-center border transition-colors",
            on ? "border-signal-cyan bg-signal-cyan/20" : "border-gotham-500 group-hover:border-gotham-400"
          )}
        />
        <Vote className="h-3 w-3 shrink-0 text-gotham-500" />
        <span className={clsx("flex-1 text-[11px]", on ? "text-gotham-100" : "text-gotham-400")}>
          Wahlergebnisse (Spektrum)
        </span>
      </button>

      {on && options && electionSelection && (
        <div className="space-y-2 pl-1">
          <select
            value={electionSelection.electionType}
            onChange={(e) => {
              const el = options.elections.find((x) => x.election_type === e.target.value);
              if (!el) return;
              const y = el.years[0];
              setElectionSelection({
                electionType: el.election_type,
                year: y.year,
                level: pickLevel(y.levels),
              });
            }}
            className="field"
          >
            {options.elections.map((e) => (
              <option key={e.election_type} value={e.election_type}>
                {e.title}
              </option>
            ))}
          </select>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={electionSelection.year}
              onChange={(e) => {
                const y = current?.years.find((x) => x.year === Number(e.target.value));
                if (!y) return;
                setElectionSelection({
                  ...electionSelection,
                  year: y.year,
                  level: y.levels.includes(electionSelection.level)
                    ? electionSelection.level
                    : pickLevel(y.levels),
                });
              }}
              className="field"
            >
              {current?.years.map((y) => (
                <option key={y.year} value={y.year}>
                  {y.year}
                </option>
              ))}
            </select>
            <select
              value={electionSelection.level}
              onChange={(e) => setElectionSelection({ ...electionSelection, level: e.target.value })}
              className="field"
            >
              {currentYear?.levels.map((l) => (
                <option key={l} value={l}>
                  {LEVEL_LABELS[l] ?? l}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: In `CatalogPanel.tsx` einbinden**

Import oben ergänzen:

```tsx
import ElectionsControl from "./ElectionsControl";
```

Im JSX: der Block `{activeEntries.length > 0 && (…Active stack…)}` bleibt; direkt danach (noch innerhalb von `open && (<div className="px-3 py-3">…`)) einfügen:

```tsx
            <ElectionsControl />
```

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ElectionsControl.tsx frontend/src/components/CatalogPanel.tsx
git commit -m "Add elections spectrum control to catalog panel

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Hover-Tooltip-Komponente mit Pie-Chart

**Files:**
- Create: `frontend/src/components/ElectionSpectrumTooltip.tsx`

**Interfaces:**
- Consumes: Typen + `SPECTRUM_DOMAIN` aus `../api/elections` (Task 7); Recharts (`PieChart`, `Pie`, `Cell`).
- Produces (von Task 10 konsumiert):
  - `parseSpectrumProps(raw: Record<string, unknown>): SpectrumFeatureProps` — MapLibre liefert `parties` als JSON-String.
  - `ElectionTooltipContent({ props }: { props: SpectrumFeatureProps })` — Inhalt (auch für Klick-Popup).
  - Default-Export `ElectionSpectrumTooltip({ hover }: { hover: { x: number; y: number; props: SpectrumFeatureProps } })` — cursor-folgender Container.

- [ ] **Step 1: Komponente anlegen** — `frontend/src/components/ElectionSpectrumTooltip.tsx`:

```tsx
import { PieChart, Pie, Cell } from "recharts";
import { SPECTRUM_DOMAIN, SpectrumFeatureProps, SpectrumPartyShare } from "../api/elections";

/** MapLibre serialisiert verschachtelte GeoJSON-Properties als JSON-String. */
export function parseSpectrumProps(raw: Record<string, unknown>): SpectrumFeatureProps {
  const parties: SpectrumPartyShare[] =
    typeof raw.parties === "string"
      ? JSON.parse(raw.parties)
      : ((raw.parties as SpectrumPartyShare[]) ?? []);
  return {
    gebiet_code: String(raw.gebiet_code ?? ""),
    name: String(raw.name ?? ""),
    score: typeof raw.score === "number" ? raw.score : null,
    coverage_pct: Number(raw.coverage_pct ?? 0),
    turnout_pct: typeof raw.turnout_pct === "number" ? raw.turnout_pct : null,
    parties,
  };
}

/** Score → Farbe der Rot↔Grau↔Blau-Skala (identisch zur Map-Interpolation). */
export function scoreColor(score: number | null): string {
  if (score === null) return "#6b7683";
  const stops: [number, [number, number, number]][] = [
    [-SPECTRUM_DOMAIN, [229, 72, 77]],   // #e5484d
    [0, [58, 64, 72]],                   // #3a4048
    [SPECTRUM_DOMAIN, [59, 130, 246]],   // #3b82f6
  ];
  const s = Math.max(-SPECTRUM_DOMAIN, Math.min(SPECTRUM_DOMAIN, score));
  const [x0, c0] = s <= 0 ? stops[0] : stops[1];
  const [x1, c1] = s <= 0 ? stops[1] : stops[2];
  const t = (s - x0) / (x1 - x0);
  const rgb = c0.map((v, i) => Math.round(v + t * (c1[i] - v)));
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

export function ElectionTooltipContent({ props }: { props: SpectrumFeatureProps }) {
  const top = props.parties.slice(0, 6);
  return (
    <div className="px-3 py-2">
      <div className="mb-1.5 flex items-center justify-between gap-3 border-b border-gotham-700 pb-1.5">
        <span className="truncate text-[12px] font-medium text-gotham-100">{props.name}</span>
        <span
          className="shrink-0 border px-1.5 py-0.5 font-mono text-[10px]"
          style={{ color: scoreColor(props.score), borderColor: scoreColor(props.score) }}
        >
          {props.score === null ? "–" : props.score.toFixed(2)}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <PieChart width={110} height={110}>
          <Pie
            data={props.parties}
            dataKey="share"
            nameKey="name"
            cx="50%"
            cy="50%"
            innerRadius={26}
            outerRadius={52}
            strokeWidth={0}
            isAnimationActive={false}
          >
            {props.parties.map((p) => (
              <Cell key={p.name} fill={p.color} />
            ))}
          </Pie>
        </PieChart>
        <div className="min-w-0 flex-1 space-y-0.5">
          {top.map((p) => (
            <div key={p.name} className="flex items-center gap-1.5 font-mono text-[10px]">
              <span className="h-1.5 w-1.5 shrink-0" style={{ backgroundColor: p.color }} />
              <span className="min-w-0 flex-1 truncate text-gotham-300">{p.name}</span>
              <span className="text-gotham-100">{p.share.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-1.5 border-t border-gotham-800 pt-1 font-mono text-[9px] text-gotham-500">
        {props.turnout_pct !== null && <>Wahlbeteiligung {props.turnout_pct.toFixed(1)}% · </>}
        {props.coverage_pct.toFixed(0)}% der Stimmen im Score
      </div>
    </div>
  );
}

export default function ElectionSpectrumTooltip({
  hover,
}: {
  hover: { x: number; y: number; props: SpectrumFeatureProps };
}) {
  return (
    <div
      className="pointer-events-none absolute z-20 w-64 border border-gotham-700 bg-gotham-900/95 shadow-xl backdrop-blur-sm"
      style={{
        left: Math.min(hover.x + 14, window.innerWidth - 280),
        top: hover.y + 14,
      }}
    >
      <ElectionTooltipContent props={hover.props} />
    </div>
  );
}
```

- [ ] **Step 2: Lint**

Run: `cd frontend && npm run lint`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ElectionSpectrumTooltip.tsx
git commit -m "Add election spectrum hover tooltip with party pie chart

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: MapView — Spektrum-Layer, Hover, Klick-Fallback, Legende

**Files:**
- Modify: `frontend/src/components/MapView.tsx`

**Interfaces:**
- Consumes: `fetchSpectrum`, `SPECTRUM_DOMAIN`, `SpectrumFeatureProps` (Task 7); `ElectionSpectrumTooltip`, `ElectionTooltipContent`, `parseSpectrumProps` (Task 9); mapStore `electionSelection` (Task 7).
- Produces: Layer-IDs `elections-fill`/`elections-line`; erweitertes `PopupInfo` mit `kind?: "election"`.

- [ ] **Step 1: Imports + State**

Imports ergänzen:

```tsx
import { fetchSpectrum, SPECTRUM_DOMAIN, SpectrumFeatureProps } from "../api/elections";
import ElectionSpectrumTooltip, {
  ElectionTooltipContent,
  parseSpectrumProps,
} from "./ElectionSpectrumTooltip";
```

`PopupInfo` erweitern (`kind` optional):

```tsx
interface PopupInfo {
  lng: number;
  lat: number;
  featureId: number | null;
  properties: Record<string, unknown>;
  kind?: "election";
}
```

Im Komponentenkörper: `electionSelection` mit destrukturieren (Zeile ~52) und Hover-State + Query ergänzen:

```tsx
  const {
    activeLayers, choroplethMetric, timelineYear, spatialUnit,
    selectedDatasetIds, selectedFamilyIds, electionSelection,
  } = useMapStore();

  const [electionHover, setElectionHover] = useState<{
    x: number;
    y: number;
    props: SpectrumFeatureProps;
  } | null>(null);

  const { data: spectrum } = useQuery(
    ["spectrum", electionSelection],
    () =>
      fetchSpectrum(
        electionSelection!.electionType,
        electionSelection!.year,
        electionSelection!.level
      ),
    { enabled: activeLayers.has("elections") && !!electionSelection, staleTime: 3_600_000 }
  );
```

- [ ] **Step 2: Hover- und Klick-Handler erweitern**

`handleMouseMove` ersetzen:

```tsx
  const handleMouseMove = useCallback((e: MapLayerMouseEvent) => {
    setCursor({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    if (mapRef.current) {
      mapRef.current.getCanvas().style.cursor = e.features?.length ? "pointer" : "";
    }
    const electionFeature = e.features?.find((f) => f.layer?.id === "elections-fill");
    if (electionFeature) {
      setElectionHover({
        x: e.point.x,
        y: e.point.y,
        props: parseSpectrumProps(electionFeature.properties as Record<string, unknown>),
      });
    } else {
      setElectionHover(null);
    }
  }, []);
```

In `handleClick` als ersten Zweig nach `if (!feature) return;`:

```tsx
    if (feature.layer?.id === "elections-fill") {
      setPopup({
        lng: e.lngLat.lng,
        lat: e.lngLat.lat,
        featureId: null,
        properties: feature.properties as Record<string, unknown>,
        kind: "election",
      });
      return;
    }
```

`interactiveLayerIds` um `"elections-fill"` ergänzen (in das bestehende Array).

- [ ] **Step 3: Source + Layer rendern** — nach dem Choropleth-Block (`{activeLayers.has("choropleth") && …}`):

```tsx
          {/* Politisches Spektrum (Wahlergebnisse) */}
          {activeLayers.has("elections") && spectrum && (
            <Source id="elections-spectrum" type="geojson" data={spectrum}>
              <Layer
                id="elections-fill"
                type="fill"
                paint={{
                  "fill-color": [
                    "case",
                    ["==", ["typeof", ["get", "score"]], "number"],
                    [
                      "interpolate", ["linear"], ["get", "score"],
                      -SPECTRUM_DOMAIN, "#e5484d",
                      0, "#3a4048",
                      SPECTRUM_DOMAIN, "#3b82f6",
                    ],
                    "rgba(0,0,0,0)",
                  ] as never,
                  "fill-opacity": 0.7,
                }}
              />
              <Layer
                id="elections-line"
                type="line"
                paint={{ "line-color": "#0a1015", "line-width": 0.8, "line-opacity": 0.6 }}
              />
            </Source>
          )}
```

- [ ] **Step 4: Popup-Branch + Tooltip + Legende**

Popup-Render ersetzen (der `<Popup>`-Block):

```tsx
          {popup && (
            <Popup
              longitude={popup.lng}
              latitude={popup.lat}
              closeButton
              onClose={() => setPopup(null)}
              maxWidth="300px"
            >
              {popup.kind === "election" ? (
                <ElectionTooltipContent props={parseSpectrumProps(popup.properties)} />
              ) : (
                <PopupContent featureId={popup.featureId} properties={popup.properties} />
              )}
            </Popup>
          )}
```

Nach `</Map>` (im äußeren `relative`-Container, z. B. direkt vor dem Boot-Overlay):

```tsx
      {/* Hover-Tooltip Politisches Spektrum */}
      {electionHover && <ElectionSpectrumTooltip hover={electionHover} />}

      {/* Legende Politisches Spektrum */}
      {activeLayers.has("elections") && (
        <div className="pointer-events-none absolute bottom-16 right-5 z-10 border border-gotham-700 bg-gotham-900/85 px-3 py-2 backdrop-blur-sm">
          <p className="hud-label mb-1.5 text-gotham-300">Politisches Spektrum</p>
          <div
            className="h-2 w-44"
            style={{ background: "linear-gradient(to right, #e5484d, #3a4048, #3b82f6)" }}
          />
          <div className="mt-1 flex justify-between font-mono text-[9px] text-gotham-400">
            <span>links</span>
            <span>rechts</span>
          </div>
          <p className="mt-0.5 font-mono text-[8px] text-gotham-500">Sitzordnung Bundestag</p>
        </div>
      )}
```

- [ ] **Step 5: Lint + Build**

Run: `cd frontend && npm run lint && npm run build`
Expected: 0 errors, Build erfolgreich

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/MapView.tsx
git commit -m "Render election spectrum layer with hover pie tooltip and legend

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: ElectionResultsPanel nutzt Registry-Farben

**Files:**
- Modify: `frontend/src/components/datasets/ElectionResultsPanel.tsx`

**Interfaces:**
- Consumes: `party_color` im `/elections/{id}/summary`-Response (Task 6), `SONSTIGE_COLOR` (Task 7).

- [ ] **Step 1: PARTY_COLORS-Konstante ersetzen**

Die lokale Konstante `PARTY_COLORS` (Zeilen ~23–31) löschen. Import ergänzen:

```tsx
import { SONSTIGE_COLOR } from "../../api/elections";
```

Im `parties`-Interface-Typ `party_color: string | null;` ergänzen. Die `Cell`-Farbzuweisung (bisher `PARTY_COLORS[p.party] ?? …`) ersetzen durch:

```tsx
fill={p.party_color ?? SONSTIGE_COLOR}
```

(Exakte Stelle: der `<Cell>`-Map über die Balken, Zeilen ~114–116 — dort, wo bisher `PARTY_COLORS` nachgeschlagen wird.)

- [ ] **Step 2: Lint + Build**

Run: `cd frontend && npm run lint && npm run build`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/datasets/ElectionResultsPanel.tsx
git commit -m "Use registry party colors from summary endpoint in results panel

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: Rollout auf den VPS + Ende-zu-Ende-Verifikation

**Files:** keine (Operations). **Vorbedingung: User-OK zum Push einholen — Push deployt automatisch.**

- [ ] **Step 1: Alle lokalen Tests final**

Run: `cd backend && python -m pytest tests/ -v && cd ../frontend && npm run lint && npm run build`
Expected: alles grün

- [ ] **Step 2: Push (nach User-OK)**

```bash
git push origin main
```

GitHub Actions deployt (Build + `docker compose up -d`). Warten bis durch: `gh run watch` oder ~5–10 min.

- [ ] **Step 3: Checksum-Cache der 15 Wahl-Datensätze leeren** (der Guard aus Task 1 würde beim nächsten Nightly auch allein reichen — das hier beschleunigt auf sofort)

```bash
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech 'docker exec -i leipzig-data-db-1 psql -U leipzig -d leipzig_data' <<'SQL'
DELETE FROM raw_ingest.dataset_checksums WHERE dataset_id IN (
  'fff8cfc0-a4aa-4627-89ed-a46bb6a29c59','f5b27739-e3dd-49ca-95cd-9b0e9b907684',
  '8354f558-9291-44a4-b487-35577e5ea2ec','510a0409-744b-4462-87ec-832057c1df38',
  '19ea44b0-1d0f-4e4e-b6e4-4f4d5bcc0c90','4b9c85a0-63a1-406f-923e-1df14295f3ed',
  'bf7b851d-592c-425c-9f11-704966305147','0e7e9fa6-5d6a-4301-b991-5dad6c6f027e',
  'c1bac74a-cdd2-4116-8ba9-ff2c2c7aa6b0','5be18d85-d375-4849-9a8b-8c222f53c1d4',
  '4db3895e-92a9-4bb7-bb33-f792178d331f','3700e4dc-bb3e-483c-b285-f25b1aea806e',
  'b03dcd68-b921-4356-b2b8-5f28669e8e50','1ae46e0e-af40-439e-9ad8-eb5abf81679d',
  '4f261ede-a4c6-4815-a773-6d975c0a8ae5');
SQL
```

Expected: `DELETE 15` (oder weniger, falls Einträge fehlen).

- [ ] **Step 4: Wahl-CSVs sofort laden** (statt auf 02:00 UTC zu warten)

```bash
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech 'docker exec -i leipzig-data-etl-1 python' <<'PY'
import json
from src.pipeline import run_dataset
contracts = {c["id"]: c for c in json.load(open("/app/dataset_contracts.json"))}
ids = ["fff8cfc0-a4aa-4627-89ed-a46bb6a29c59","f5b27739-e3dd-49ca-95cd-9b0e9b907684",
       "8354f558-9291-44a4-b487-35577e5ea2ec","510a0409-744b-4462-87ec-832057c1df38",
       "19ea44b0-1d0f-4e4e-b6e4-4f4d5bcc0c90","4b9c85a0-63a1-406f-923e-1df14295f3ed",
       "bf7b851d-592c-425c-9f11-704966305147","0e7e9fa6-5d6a-4301-b991-5dad6c6f027e",
       "c1bac74a-cdd2-4116-8ba9-ff2c2c7aa6b0","5be18d85-d375-4849-9a8b-8c222f53c1d4",
       "4db3895e-92a9-4bb7-bb33-f792178d331f","3700e4dc-bb3e-483c-b285-f25b1aea806e",
       "b03dcd68-b921-4356-b2b8-5f28669e8e50","1ae46e0e-af40-439e-9ad8-eb5abf81679d",
       "4f261ede-a4c6-4815-a773-6d975c0a8ae5"]
for i in ids:
    print(i[:8], run_dataset(contracts[i]))
PY
```

Expected: je Zeile `('success', <n>, <m>)` mit m > 0.

- [ ] **Step 5: MatView refreshen + Daten verifizieren**

```bash
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech 'docker exec -i leipzig-data-db-1 psql -U leipzig -d leipzig_data' <<'SQL'
REFRESH MATERIALIZED VIEW mart.election_party_shares;
SELECT election_id, level, count(*) FROM core.election_results GROUP BY 1,2 ORDER BY 1,2;
SELECT election_type, source, count(DISTINCT year) AS jahre, count(*) AS rows
FROM mart.election_party_shares GROUP BY 1,2 ORDER BY 1,2;
SELECT election_type, year, level, round(avg(share_pct)::numeric,1) AS avg_share, count(*) FILTER (WHERE party_key IS NOT NULL) AS gemappt, count(*) AS gesamt
FROM mart.election_party_shares WHERE election_type='bundestagswahl' GROUP BY 1,2,3 ORDER BY 2 DESC LIMIT 6;
SQL
```

Expected: `election_results` mit Zeilen für alle 5 Wahlen; MatView mit `results`- UND `statistik`-Zeilen je Wahltyp; Kollisionsregel sichtbar (z. B. bundestagswahl 2025/wahlbezirk aus `results`, 2017/ortsteil aus `statistik`); gemappt > 0.

- [ ] **Step 6: Redis-Cache leeren** (sonst liefern die 1h-gecachten Endpoints noch leere Antworten)

```bash
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech 'docker exec leipzig-data-redis-1 redis-cli FLUSHDB'
```

- [ ] **Step 7: E2E im Browser**

Dashboard öffnen → Datenkatalog → „Wahlergebnisse (Spektrum)“ aktivieren. Prüfen: (a) Karte färbt Gebiete rot↔blau, Legende sichtbar; (b) Hover zeigt Tooltip mit Pie + Prozentliste + Wahlbeteiligung/Abdeckung; (c) Wahltyp-Wechsel (BTW → EW → LTW → SRW → OBM), Jahr-Wechsel (auch historisch, z. B. BTW 2005), Ebenen-Wechsel (Ortsteil ↔ Wahlbezirk bei BTW 2025); (d) Klick öffnet dasselbe als Popup; (e) bestehender Statistik-Choropleth funktioniert unverändert.

- [ ] **Step 8: Plan-Datei aktualisieren (Checkboxen) + finaler Commit falls nötig**

---

## Self-Review (Plan gegen Spec)

- **Spec-Abdeckung:** Schritt 0/304-Fix → Task 1+12; Partei-Register → Task 2+4; `kleinraeumig_sources` → Task 2+4; Migration + MatView + Kollisionsregel + refresh_all → Task 3; `/elections/spectrum` + `/options` + Score/Coverage/Sonstige → Task 5+6; Summary-Farben (PARTY_COLORS-Ablösung) → Task 6+11; Frontend-Control/Layer/Legende/Hover/Klick-Fallback → Task 7–10; Tests → Task 5 (pytest), Task 12 (SQL-Smoke, E2E). Bewusste Abweichung von der Spec: `SPECTRUM_DOMAIN` lebt nur im Frontend (Spec erwähnte Domain auch im Options-Payload — Redundanz gestrichen, YAGNI).
- **Platzhalter:** keine (alle Code-Blöcke vollständig, IDs ausgeschrieben).
- **Typ-Konsistenz:** `parties`-Property `[{key,name,share,color}]` identisch in `compute_spectrum` (T5), Endpoint (T6), `SpectrumPartyShare` (T7), Tooltip (T9); `electionSelection {electionType,year,level}` identisch in Store (T7), Control (T8), MapView (T10); Layer-ID `elections-fill` konsistent (T10).
