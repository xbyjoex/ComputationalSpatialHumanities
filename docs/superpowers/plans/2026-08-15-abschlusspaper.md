# Abschlusspaper CSH — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein sechsseitiges IEEE-Paper über auerbachs-auge.tech, gestützt auf eine reproduzierbare Fallstudie zur Europawahl 2024 — nachdem der Stadtbezirks-Kollisionsbug im Raumschlüssel-Resolver behoben ist.

**Architecture:** Drei getrennte Schichten. (1) Ein SQL-Migrationsfix in `core.resolve_spatial_key()`, der verhindert, dass Namen einer Verwaltungsebene per Trigramm-Fuzzy-Match auf Codes einer anderen Ebene aufgelöst werden. (2) Ein reproduzierbares Analysepaket unter `paper/analysis/`, das per `ssh`+`psql` CSVs zieht und sie mit reinen, getesteten Python-Funktionen zu einer `results.json` verrechnet — jede Zahl im Paper stammt aus dieser Datei. (3) Ein IEEEtran-Dokument unter `paper/`, das Abbildungen aus `paper/figures/` und Zahlen aus `results.json` bezieht.

**Tech Stack:** PostgreSQL 16 + PostGIS (VPS) · Python 3.13 (pandas 3.0.3, numpy 2.4.6, scipy 1.17.1, matplotlib 3.10.9) · pytest 9 · TeXLive 2025 (IEEEtran) · Zugriff per `ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech`

## Global Constraints

- **Keine KI-Attribution.** Nie `Co-Authored-By: Claude`, nie `Claude-Session:`, nie „Generated with …" — nicht in Commits, PRs, Kommentaren oder Dateien. Siehe `CLAUDE.md` → *Git Conventions*.
- **Kein lokaler Container-Runtime.** Auf diesem Mac läuft kein Docker-Daemon. SQL wird ausschließlich auf dem VPS ausgeführt; Python wird lokal in einem venv getestet.
- **Arbeitsbranch:** `paper/abschlusspaper`. Nicht auf `main` committen.
- **Jede Zahl im Paper stammt aus `paper/analysis/results.json`.** Keine Zahl von Hand in `main.tex` schreiben, die nicht dort steht.
- **Bezugsjahr durchgängig 2024**, Wahl durchgängig `ew2024`.
- **Wortbudget 3.980**, Zielumfang 6 Seiten. Kürzungsreihenfolge steht in der Spec, Abschnitt 9.
- **Spec:** `docs/superpowers/specs/2026-08-15-abschlusspaper-design.md` — bei jedem Widerspruch gilt die Spec.
- **Datensatz-IDs** (immer als Paar mit dem Metriknamen verwenden, nie den Namen allein):
  - `30943d88-4ac9-4968-84bc-35e9b337a85d` — Arbeitslose (Jahreszahlen, kleinräumig)
  - `dcc45e1a-11d1-4922-80c3-f49ba12863fb` — Einwohner (Jahreszahlen, kleinräumig)
  - `aa01ad81-1060-48e9-84f2-8908287ecf5e` — Familien mit Kindern (Jahreszahlen, kleinräumig)
- **Plausibilitätsanker:** Summe `Einwohner insgesamt` 2024 über die 63 Ortsteile = **632.560**. Weicht sie ab, ist die Extraktion falsch — nicht weiterarbeiten.
  - Verifiziert am 2026-08-15: Der Datensatz enthält 74 Zeilen = 63 Ortsteile + 10 Stadtbezirke + 1 Stadtgesamt. Ortsteile **und** Stadtbezirke summieren sich unabhängig voneinander auf **exakt 632.560**; die Zeile `Stadt Leipzig` nennt **632.562**. Die Differenz von 2 sind Einwohner ohne Ortsteilzuordnung, die das Statistikamt nur in die Stadtsumme faltet — kein Extraktionsverlust. **Nicht** gegen 632.562 prüfen.

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| `sql/migrations/018_spatial_key_level_guard.sql` | Ebenenprüfung im Resolver + einmaliges Zurücksetzen der falsch aufgelösten Codes |
| `paper/analysis/extract.sh` | Zieht fünf CSVs per `ssh`+`psql` nach `paper/analysis/data/` |
| `paper/analysis/indicators.py` | Reine Funktionen: Indikatortabelle bauen, Anteile bilden, auf Stadtbezirke aggregieren |
| `paper/analysis/correlate.py` | Reine Funktionen: Pearson r, R², p-Wert |
| `paper/analysis/run.py` | Orchestriert CSV → `results.json`; enthält alle Plausibilitätsprüfungen |
| `paper/tests/test_indicators.py` | Tests für Aggregation und Anteilsbildung |
| `paper/tests/test_correlate.py` | Tests für die Korrelationsrechnung |
| `paper/figures/make_figures.py` | Erzeugt Abb. 2–4 als Vektor-PDF aus `results.json` |
| `paper/main.tex` | IEEEtran-Dokument |
| `paper/refs.bib` | Literaturverzeichnis |
| `paper/Makefile` | `make analysis`, `make figures`, `make paper`, `make all` |

**Warum getrennt:** `extract.sh` ist die einzige Stelle mit Netzwerk- und DB-Kontakt. `indicators.py` und `correlate.py` sind rein und damit ohne Datenbank testbar — genau dort entstehen die stillen Fehler. `run.py` verdrahtet beides und ist die einzige Quelle der Zahlen.

**Bewusst nicht im Plan:** Die Umklassifizierung der Stadtbezirks-Zeilen von `spatial_unit='ortsteil'` nach `'stadtbezirk'`. Das wäre technisch reizvoll (native Stadtbezirks-Indikatoren), ist aber für die MAUP-Demo **methodisch schlechter**: Ein sauberer MAUP-Nachweis braucht *dieselben* Daten, zweimal anders zoniert. Nähme man amtliche Stadtbezirkswerte, vermischte man Zonierungseffekt und Definitionsunterschied. Wir aggregieren selbst — und prüfen das Ergebnis gegen die amtlichen Zeilen (Task 5).

---

## Task 1: Resolver-Fix und Neuauflösung

**Files:**
- Create: `sql/migrations/018_spatial_key_level_guard.sql`

**Interfaces:**
- Consumes: bestehende `core.resolve_spatial_key(p_unit TEXT, p_raw TEXT)` aus `sql/migrations/009_families_and_spatial_normalization.sql:71-93`
- Produces: dieselbe Signatur, um eine Ebenenprüfung im Fuzzy-Zweig erweitert; `core.statistics.spatial_code` ist danach NULL für alle Zeilen, deren `spatial_key` exakt eine andere Verwaltungsebene benennt

**Hintergrund.** `resolve_spatial_key` probiert vier Zweige in dieser Reihenfolge: exakter Alias → Roh-Wert ist bereits ein Code → führende Ziffern → **Trigramm-Fuzzy-Match `similarity > 0.45`**. Zweig 4 ist der Fehler: `similarity('grunau-mitte', 'mitte')` liegt über der Schwelle, also wird der **Stadtbezirk** „Mitte" auf den **Ortsteil**-Code `62` (Grünau-Mitte) abgebildet. Ebenso `Südost`→`02` und `Nordwest`→`05`. Betroffen: 13.862 Zeilen in 42 Datensätzen.

- [ ] **Step 1: Vorher-Zustand auf dem VPS festhalten**

```bash
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech "docker exec leipzig-data-db-1 psql -U leipzig -d leipzig_data -A -F'|' -c \"
SELECT s.spatial_key, s.spatial_code, count(*) rows, count(DISTINCT s.dataset_id) datasets
FROM core.statistics s
JOIN core.admin_boundaries sb ON sb.boundary_type='stadtbezirk' AND sb.name = s.spatial_key
WHERE s.spatial_unit='ortsteil' AND s.spatial_code IS NOT NULL
GROUP BY 1,2 ORDER BY 3 DESC;
\""
```

Erwartet: genau drei Zeilen — `Südost|02|4641|42`, `Mitte|62|4617|42`, `Nordwest|05|4604|42`. Summe 13.862.

- [ ] **Step 2: Migration schreiben**

Datei `sql/migrations/018_spatial_key_level_guard.sql`:

```sql
-- 018_spatial_key_level_guard.sql
--
-- Fix: core.resolve_spatial_key() mapped names of one administrative level onto
-- codes of another. The trigram fallback (branch 4) scores
-- similarity('grunau-mitte', 'mitte') above the 0.45 threshold, so the
-- Stadtbezirk "Mitte" resolved to the Ortsteil code 62. Same for
-- "Südost" -> 02 (Zentrum-Südost) and "Nordwest" -> 05 (Zentrum-Nordwest).
--
-- Root cause outside our control: the source files mix Ortsteil, Stadtbezirk and
-- city-total rows in one file without a level column, so the loader tags every
-- row with the same spatial_unit and the resolver has to guess.
--
-- 13862 rows across 42 datasets carried a wrong Ortsteil code, inflating the 2024
-- population sum to 805218 instead of the correct 632560.
--
-- Guard: never fuzzy-match a raw key that is the exact name of a *different*
-- boundary type. Exact matches (branches 1-3) are unaffected, so a name that
-- legitimately exists on the requested level still resolves.

CREATE OR REPLACE FUNCTION core.resolve_spatial_key(p_unit TEXT, p_raw TEXT)
RETURNS TEXT LANGUAGE sql STABLE AS $$
    SELECT code FROM (
        (SELECT code, 1 AS prio, 1.0 AS sim FROM core.spatial_aliases
          WHERE unit_type = p_unit AND alias = core.norm_name(p_raw))
        UNION ALL
        (SELECT code, 2, 1.0 FROM core.admin_boundaries
          WHERE boundary_type = p_unit AND code = btrim(p_raw))
        UNION ALL
        -- \y = word boundary in Postgres regex (\b would be backspace)
        (SELECT code, 3, 1.0 FROM core.admin_boundaries
          WHERE boundary_type = p_unit
            AND code = (regexp_match(btrim(p_raw), '^(\d{1,4})\y'))[1])
        UNION ALL
        (SELECT code, 4, similarity(core.norm_name(name), core.norm_name(p_raw))::float
           FROM core.admin_boundaries
          WHERE boundary_type = p_unit
            AND similarity(core.norm_name(name), core.norm_name(p_raw)) > 0.45
            AND NOT EXISTS (
                SELECT 1 FROM core.admin_boundaries other
                 WHERE other.boundary_type <> p_unit
                   AND core.norm_name(other.name) = core.norm_name(p_raw)
            )
          ORDER BY 3 DESC LIMIT 1)
    ) candidates
    ORDER BY prio, sim DESC
    LIMIT 1
$$;

-- One-time repair: drop the codes that were assigned from a foreign level name.
-- Idempotent: after the function fix, no new rows can enter this state.
UPDATE core.statistics s
   SET spatial_code = NULL
 WHERE s.spatial_code IS NOT NULL
   AND EXISTS (
       SELECT 1 FROM core.admin_boundaries other
        WHERE other.boundary_type <> s.spatial_unit
          AND core.norm_name(other.name) = core.norm_name(s.spatial_key)
   );
```

- [ ] **Step 3: Migration auf dem VPS im Trockenlauf prüfen**

Die Migration in eine Transaktion legen, verifizieren, zurückrollen. Nichts wird verändert.

```bash
scp -i ~/.ssh/leipzig_deploy sql/migrations/018_spatial_key_level_guard.sql \
    deploy@auerbachs-auge.tech:/tmp/018.sql
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech \
  "docker cp /tmp/018.sql leipzig-data-db-1:/tmp/018.sql && \
   docker exec leipzig-data-db-1 psql -U leipzig -d leipzig_data -A -F'|' -v ON_ERROR_STOP=1 -c '
BEGIN;
\\i /tmp/018.sql
SELECT count(*) AS still_wrong FROM core.statistics s
  JOIN core.admin_boundaries sb ON sb.boundary_type=\$\$stadtbezirk\$\$ AND sb.name = s.spatial_key
 WHERE s.spatial_unit=\$\$ortsteil\$\$ AND s.spatial_code IS NOT NULL;
SELECT sum(metric_value)::bigint AS einwohner_2024 FROM core.statistics
 WHERE dataset_id=\$\$dcc45e1a-11d1-4922-80c3-f49ba12863fb\$\$
   AND metric_name=\$\$Einwohner insgesamt\$\$ AND period_year=2024
   AND spatial_unit=\$\$ortsteil\$\$ AND spatial_code IS NOT NULL;
SELECT count(DISTINCT spatial_code) AS ortsteile FROM core.statistics
 WHERE dataset_id=\$\$dcc45e1a-11d1-4922-80c3-f49ba12863fb\$\$
   AND metric_name=\$\$Einwohner insgesamt\$\$ AND period_year=2024
   AND spatial_unit=\$\$ortsteil\$\$ AND spatial_code IS NOT NULL;
ROLLBACK;
'"
```

Erwartet, alle drei müssen stimmen:
- `still_wrong` = **0**
- `einwohner_2024` = **632560**
- `ortsteile` = **63**

Stimmt eine Zahl nicht, **nicht committen** — die Migration korrigieren und Step 3 wiederholen.

- [ ] **Step 4: Migration echt anwenden und in schema_migrations eintragen**

Nur ausführen, wenn Step 3 alle drei Werte bestätigt hat.

```bash
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech \
  "docker exec leipzig-data-db-1 psql -U leipzig -d leipzig_data -v ON_ERROR_STOP=1 \
     -c '\\i /tmp/018.sql' \
     -c \"INSERT INTO public.schema_migrations(filename) VALUES ('018_spatial_key_level_guard.sql') ON CONFLICT DO NOTHING\""
```

Der `schema_migrations`-Eintrag verhindert, dass der ETL-Scheduler die Datei beim nächsten Start erneut anwendet. Die Migration ist ohnehin idempotent, aber der Eintrag hält die Buchführung ehrlich.

- [ ] **Step 5: Nachher-Zustand verifizieren**

```bash
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech "docker exec leipzig-data-db-1 psql -U leipzig -d leipzig_data -A -F'|' -c \"
SELECT 'still_wrong' k, count(*)::text v FROM core.statistics s
  JOIN core.admin_boundaries sb ON sb.boundary_type='stadtbezirk' AND sb.name = s.spatial_key
 WHERE s.spatial_unit='ortsteil' AND s.spatial_code IS NOT NULL
UNION ALL SELECT 'einwohner_2024', sum(metric_value)::bigint::text FROM core.statistics
 WHERE dataset_id='dcc45e1a-11d1-4922-80c3-f49ba12863fb' AND metric_name='Einwohner insgesamt'
   AND period_year=2024 AND spatial_unit='ortsteil' AND spatial_code IS NOT NULL
UNION ALL SELECT 'resolver_mitte', coalesce(core.resolve_spatial_key('ortsteil','Mitte'),'NULL')
UNION ALL SELECT 'resolver_gruenau_mitte', coalesce(core.resolve_spatial_key('ortsteil','Grünau-Mitte'),'NULL')
UNION ALL SELECT 'resolver_stadtbezirk_mitte', coalesce(core.resolve_spatial_key('stadtbezirk','Mitte'),'NULL');
\""
```

Erwartet: `still_wrong=0` · `einwohner_2024=632560` · `resolver_mitte=NULL` · `resolver_gruenau_mitte=62` · `resolver_stadtbezirk_mitte` = der Stadtbezirks-Code für Mitte (nicht NULL — die Auflösung auf der *richtigen* Ebene muss weiter funktionieren).

- [ ] **Step 6: Commit**

```bash
git add sql/migrations/018_spatial_key_level_guard.sql
git commit -m "Stop resolving spatial keys across administrative levels

The trigram fallback in core.resolve_spatial_key() matched the Stadtbezirk
names Mitte, Südost and Nordwest onto the Ortsteil codes 62, 02 and 05,
because similarity('grunau-mitte', 'mitte') clears the 0.45 threshold. Source
files mix Ortsteil, Stadtbezirk and city-total rows without a level column, so
the resolver had to guess and guessed wrong on three names.

13862 rows across 42 datasets carried a foreign-level code; the 2024 population
summed to 805218 instead of 632560. The fuzzy branch now refuses any raw key
that exactly names a different boundary type, and the migration clears the
codes that were already assigned that way."
```

---

## Task 2: Reine Analysefunktionen mit Tests

**Files:**
- Create: `paper/analysis/indicators.py`
- Create: `paper/analysis/correlate.py`
- Create: `paper/tests/test_indicators.py`
- Create: `paper/tests/test_correlate.py`
- Create: `paper/requirements.txt`

**Interfaces:**
- Produces:
  - `indicators.build_counts(rows: list[dict]) -> dict[str, dict[str, float]]` — `{spatial_code: {metric_key: value}}`, `metric_key` ist `f"{dataset_id}:{metric_name}"`
  - `indicators.compute_shares(counts: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]` — je Code die drei Anteile `unemployment`, `foreign`, `single_parent`
  - `indicators.aggregate_to_parent(counts: dict[str, dict[str, float]], parent_of: dict[str, str]) -> dict[str, dict[str, float]]`
  - `correlate.pearson(xs: list[float], ys: list[float]) -> dict` — `{"r": float, "r2": float, "p": float, "n": int}`

- [ ] **Step 1: requirements.txt anlegen**

```
pandas==3.0.3
numpy==2.4.6
scipy==1.17.1
matplotlib==3.10.9
pytest==9.0.3
```

- [ ] **Step 2: venv anlegen und installieren**

```bash
python3 -m venv paper/.venv
paper/.venv/bin/pip install -q -r paper/requirements.txt
paper/.venv/bin/pytest --version
```

Erwartet: `pytest 9.0.3`

- [ ] **Step 3: Failing tests für indicators.py schreiben**

Datei `paper/tests/test_indicators.py`:

```python
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
```

- [ ] **Step 4: Tests laufen lassen, Fehlschlag bestätigen**

```bash
paper/.venv/bin/pytest paper/tests/test_indicators.py -v
```

Erwartet: FAIL — `ModuleNotFoundError: No module named 'analysis'`

- [ ] **Step 5: indicators.py implementieren**

Datei `paper/analysis/indicators.py`:

```python
"""Pure indicator maths for the CSH paper case study.

No database access here on purpose: everything below is a plain transformation
of already-extracted rows, so it can be tested without a Postgres instance.

Metric names in core.statistics are NOT unique — 56 of 300 Ortsteil-level names
occur in more than one dataset, and 'Ausländer' alone exists in six with six
different base populations. Every value is therefore keyed by the pair
(dataset_id, metric_name), never by the metric name alone.
"""

from __future__ import annotations

ARBEITSLOSE = "30943d88-4ac9-4968-84bc-35e9b337a85d:Arbeitslose insgesamt"
EINWOHNER = "dcc45e1a-11d1-4922-80c3-f49ba12863fb:Einwohner insgesamt"
AUSLAENDER = "dcc45e1a-11d1-4922-80c3-f49ba12863fb:Ausländer"
FAMILIEN = "aa01ad81-1060-48e9-84f2-8908287ecf5e:Familien insgesamt"
ALLEINERZ = "aa01ad81-1060-48e9-84f2-8908287ecf5e:Alleinerziehende insgesamt"

SHARE_DEFINITIONS = {
    "unemployment": (ARBEITSLOSE, EINWOHNER),
    "foreign": (AUSLAENDER, EINWOHNER),
    "single_parent": (ALLEINERZ, FAMILIEN),
}


def metric_key(dataset_id: str, metric_name: str) -> str:
    return f"{dataset_id}:{metric_name}"


def build_counts(rows) -> dict[str, dict[str, float]]:
    """Group extracted statistics rows into {spatial_code: {metric_key: value}}."""
    counts: dict[str, dict[str, float]] = {}
    for row in rows:
        code = row["spatial_code"]
        key = metric_key(row["dataset_id"], row["metric_name"])
        counts.setdefault(code, {})[key] = float(row["metric_value"])
    return counts


def compute_shares(counts: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """Derive the three ratios from summable counts, per spatial unit."""
    shares: dict[str, dict[str, float]] = {}
    for code, metrics in counts.items():
        out: dict[str, float] = {}
        for name, (numerator, denominator) in SHARE_DEFINITIONS.items():
            num = metrics.get(numerator)
            den = metrics.get(denominator)
            if num is None or den in (None, 0):
                continue
            out[name] = num / den
        if out:
            shares[code] = out
    return shares


def aggregate_to_parent(
    counts: dict[str, dict[str, float]], parent_of: dict[str, str]
) -> dict[str, dict[str, float]]:
    """Sum counts up to the parent unit (Ortsteil -> Stadtbezirk).

    Counts are summed; ratios are recomputed afterwards via compute_shares().
    Averaging the child ratios instead would silently weight a 500-resident
    Ortsteil the same as a 30000-resident one.
    """
    agg: dict[str, dict[str, float]] = {}
    for code, metrics in counts.items():
        parent = parent_of.get(code)
        if parent is None:
            continue
        bucket = agg.setdefault(parent, {})
        for key, value in metrics.items():
            bucket[key] = bucket.get(key, 0.0) + value
    return agg
```

- [ ] **Step 6: Tests laufen lassen, Erfolg bestätigen**

```bash
paper/.venv/bin/pytest paper/tests/test_indicators.py -v
```

Erwartet: 5 passed

- [ ] **Step 7: Failing tests für correlate.py schreiben**

Datei `paper/tests/test_correlate.py`:

```python
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
```

- [ ] **Step 8: Tests laufen lassen, Fehlschlag bestätigen**

```bash
paper/.venv/bin/pytest paper/tests/test_correlate.py -v
```

Erwartet: FAIL — `ModuleNotFoundError: No module named 'analysis.correlate'`

- [ ] **Step 9: correlate.py implementieren**

Datei `paper/analysis/correlate.py`:

```python
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
```

- [ ] **Step 10: Tests laufen lassen, Erfolg bestätigen**

```bash
paper/.venv/bin/pytest paper/tests -v
```

Erwartet: 9 passed

- [ ] **Step 11: .gitignore ergänzen und committen**

An `.gitignore` anhängen:

```
paper/.venv/
paper/**/__pycache__/
paper/*.aux
paper/*.log
paper/*.out
paper/*.bbl
paper/*.blg
```

```bash
git add .gitignore paper/requirements.txt paper/analysis/indicators.py paper/analysis/correlate.py paper/tests/
git commit -m "Add tested indicator and correlation maths for the paper case study

Indicators are keyed by (dataset_id, metric_name) because metric names are not
unique in core.statistics. Aggregation sums counts and recomputes ratios
afterwards, so the Stadtbezirk share is population-weighted by construction
rather than an unweighted mean of Ortsteil shares."
```

---

## Task 3: Extraktion der fünf CSVs

**Files:**
- Create: `paper/analysis/extract.sh`
- Create: `paper/analysis/data/` (durch das Skript befüllt)

**Interfaces:**
- Consumes: die Datenbank nach Task 1 (Resolver gefixt)
- Produces: fünf CSVs mit Kopfzeile in `paper/analysis/data/` — `indicators_ortsteil.csv`, `election_ortsteil.csv`, `election_stadtbezirk.csv`, `boundaries.csv`, `indicators_stadtbezirk_raw.csv`

**Warum trotz Task 1 noch ein Guard in den Abfragen:** Doppelte Absicherung. Der Resolver-Fix verhindert die Fehlauflösung künftig, aber der Guard in der Abfrage dokumentiert im Paper nachvollziehbar, dass geprüft wurde — und schützt gegen einen versehentlich zurückgerollten Fix.

- [ ] **Step 1: extract.sh schreiben**

Datei `paper/analysis/extract.sh`:

```bash
#!/usr/bin/env bash
# Pull every input the case study needs into paper/analysis/data/ as CSV.
#
# All SQL runs on the VPS: there is no local Postgres. Each query writes one
# CSV with a header row. Re-running is safe and overwrites.
set -euo pipefail

SSH_TARGET="deploy@auerbachs-auge.tech"
SSH_KEY="${HOME}/.ssh/leipzig_deploy"
DATA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/data"
mkdir -p "$DATA_DIR"

YEAR=2024
ELECTION=ew2024

# The three curated datasets. Metric names alone are ambiguous, so every pair is
# pinned explicitly.
PAIRS="
     (s.dataset_id = '30943d88-4ac9-4968-84bc-35e9b337a85d' AND s.metric_name = 'Arbeitslose insgesamt')
  OR (s.dataset_id = 'dcc45e1a-11d1-4922-80c3-f49ba12863fb' AND s.metric_name IN ('Einwohner insgesamt','Ausländer'))
  OR (s.dataset_id = 'aa01ad81-1060-48e9-84f2-8908287ecf5e' AND s.metric_name IN ('Familien insgesamt','Alleinerziehende insgesamt'))
"

# Rows whose spatial_key is exactly the name of a different administrative level
# belong to that level, not to this one. Belt and braces alongside migration 018.
FOREIGN_LEVEL_GUARD="
  NOT EXISTS (
    SELECT 1 FROM core.admin_boundaries other
     WHERE other.boundary_type <> s.spatial_unit
       AND core.norm_name(other.name) = core.norm_name(s.spatial_key)
  )
"

run_query() {
  local outfile="$1"
  local sql="$2"
  echo "  -> ${outfile}"
  ssh -i "$SSH_KEY" -o BatchMode=yes "$SSH_TARGET" \
    "docker exec leipzig-data-db-1 psql -U leipzig -d leipzig_data -v ON_ERROR_STOP=1 \
       -c \"COPY (${sql}) TO STDOUT WITH CSV HEADER\"" > "${DATA_DIR}/${outfile}"
}

echo "Extracting case-study inputs (year ${YEAR}, election ${ELECTION})"

run_query indicators_ortsteil.csv "
  SELECT DISTINCT s.spatial_code, b.name AS ortsteil, s.dataset_id, s.metric_name, s.metric_value
  FROM core.statistics s
  JOIN core.admin_boundaries b
    ON b.boundary_type = 'ortsteil' AND b.code = s.spatial_code
  WHERE s.spatial_unit = 'ortsteil'
    AND s.period_year = ${YEAR}
    AND s.spatial_code IS NOT NULL
    AND ${FOREIGN_LEVEL_GUARD}
    AND (${PAIRS})
  ORDER BY s.spatial_code, s.dataset_id, s.metric_name
"

run_query election_ortsteil.csv "
  SELECT spatial_code, gebiet_name, party, zweitstimmen, gueltige_zweit,
         wahlberechtigte, waehler
  FROM core.election_results
  WHERE election_id = '${ELECTION}' AND level = 'ortsteil' AND spatial_code IS NOT NULL
  ORDER BY spatial_code, party
"

run_query election_stadtbezirk.csv "
  SELECT spatial_code, gebiet_name, party, zweitstimmen, gueltige_zweit,
         wahlberechtigte, waehler
  FROM core.election_results
  WHERE election_id = '${ELECTION}' AND level = 'stadtbezirk' AND spatial_code IS NOT NULL
  ORDER BY spatial_code, party
"

run_query boundaries.csv "
  SELECT boundary_type, code, name, parent_code
  FROM core.admin_boundaries
  WHERE boundary_type IN ('ortsteil','stadtbezirk')
  ORDER BY boundary_type, code
"

# Validation input only: the Stadtbezirk rows that migration 018 unlinked. Our
# own Ortsteil -> Stadtbezirk sums must reproduce these official values.
run_query indicators_stadtbezirk_raw.csv "
  SELECT sb.code AS stadtbezirk_code, sb.name AS stadtbezirk,
         s.dataset_id, s.metric_name, s.metric_value
  FROM core.statistics s
  JOIN core.admin_boundaries sb
    ON sb.boundary_type = 'stadtbezirk'
   AND core.norm_name(sb.name) = core.norm_name(s.spatial_key)
  WHERE s.spatial_unit = 'ortsteil'
    AND s.period_year = ${YEAR}
    AND (${PAIRS})
  ORDER BY sb.code, s.dataset_id, s.metric_name
"

echo "Done. Files in ${DATA_DIR}:"
wc -l "${DATA_DIR}"/*.csv
```

- [ ] **Step 2: Ausführbar machen und laufen lassen**

```bash
chmod +x paper/analysis/extract.sh
paper/analysis/extract.sh
```

Erwartet: fünf Dateien, jede mit mehr als einer Zeile. `indicators_ortsteil.csv` muss **316** Zeilen haben (63 Ortsteile × 5 Metriken + Kopfzeile).

- [ ] **Step 3: Plausibilität der Extraktion von Hand prüfen**

```bash
python3 - <<'PY'
import csv
from collections import defaultdict
rows = list(csv.DictReader(open("paper/analysis/data/indicators_ortsteil.csv")))
by_metric = defaultdict(float)
codes = set()
for r in rows:
    by_metric[(r["dataset_id"][:8], r["metric_name"])] += float(r["metric_value"])
    codes.add(r["spatial_code"])
print("distinct Ortsteile:", len(codes))
for k, v in sorted(by_metric.items()):
    print(f"{k[0]} {k[1]:<32} {v:>12,.0f}")
PY
```

Erwartet: `distinct Ortsteile: 63` und für `dcc45e1a Einwohner insgesamt` exakt **632.560**.
Weicht der Wert ab, ist Task 1 nicht sauber angewendet — dort zurück, nicht hier weiterbasteln.

- [ ] **Step 4: Commit**

```bash
git add paper/analysis/extract.sh paper/analysis/data/
git commit -m "Extract the case study inputs as CSV

Five queries, all pinned to (dataset_id, metric_name) pairs and guarded against
rows whose spatial_key names a different administrative level. The extracted
CSVs are committed so the analysis is reproducible without database access."
```

---

## Task 4: Fallstudie auf Ortsteilebene

**Files:**
- Create: `paper/analysis/run.py`
- Create: `paper/analysis/results.json` (erzeugt)

**Interfaces:**
- Consumes: `indicators.build_counts`, `indicators.compute_shares`, `correlate.pearson`, die CSVs aus Task 3
- Produces: `paper/analysis/results.json` mit den Schlüsseln `meta`, `coverage`, `ortsteil`, `stadtbezirk`, `maup`, `validation`

- [ ] **Step 1: run.py mit Ortsteil-Auswertung schreiben**

Datei `paper/analysis/run.py`:

```python
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
```

- [ ] **Step 2: Laufen lassen**

```bash
cd paper/analysis && ../.venv/bin/python run.py; cd - >/dev/null
```

Erwartet: `n=63 Ortsteile` und eine Liste der acht stärksten Korrelationen. Bricht das Skript mit der Populationsmeldung ab, ist Task 1 nicht angewendet.

- [ ] **Step 3: Parteinamen gegen die Daten abgleichen**

Die Liste `PARTIES` muss den tatsächlichen `party`-Werten entsprechen.

```bash
python3 -c "
import csv,collections
rows=list(csv.DictReader(open('paper/analysis/data/election_ortsteil.csv')))
tot=collections.Counter()
for r in rows: tot[r['party']]+=int(r['zweitstimmen'] or 0)
for p,v in tot.most_common(12): print(f'{p:<24}{v:>8,}')
"
```

Passe `PARTIES` in `run.py` an die sechs stimmstärksten Listen an, falls die Schreibweise abweicht, und lass Step 2 erneut laufen.

- [ ] **Step 4: Commit**

```bash
git add paper/analysis/run.py paper/analysis/results.json
git commit -m "Compute the Ortsteil-level case study into results.json

Party shares come from zweitstimmen/gueltige_zweit; the Europawahl carries no
erststimmen. The run aborts unless the population sums to 632560 across exactly
63 Ortsteile, so a regressed spatial-key fix cannot quietly produce plausible
but wrong correlations."
```

---

## Task 5: MAUP-Demonstration

**Files:**
- Modify: `paper/analysis/run.py`

**Interfaces:**
- Consumes: `indicators.aggregate_to_parent`, `boundaries.csv`, `election_stadtbezirk.csv`, `indicators_stadtbezirk_raw.csv`
- Produces: die Schlüssel `stadtbezirk`, `maup` und `validation` in `results.json`

**Methodik.** Wahlergebnisse liegen für `ew2024` amtlich auf beiden Ebenen vor — sie sind dieselben Stimmen, nur anders summiert. Die Sozialindikatoren liegen nur auf Ortsteilebene vor und werden über `parent_code` selbst aggregiert. Diese eigene Aggregation wird gegen die amtlichen Stadtbezirks-Zeilen geprüft, die Migration 018 abgehängt hat — dieselben Zeilen, die den Bug verursacht haben, beweisen jetzt die Korrektheit der Aggregation.

- [ ] **Step 1: Aggregation und Validierung in run.py ergänzen**

In `run.py` vor `def main()` einfügen:

```python
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
```

- [ ] **Step 2: main() um den Stadtbezirks-Zweig erweitern**

In `main()` direkt vor dem `results = {`-Block einfügen:

```python
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
```

Und den `results`-Dict um drei Schlüssel erweitern (nach `"ortsteil": {...},`):

```python
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
```

Dafür muss die Ortsteil-Korrelation vorher in eine lokale Variable gezogen werden. Ersetze in `main()` die Zeile

```python
            "correlations": correlate_grid(votes_ot, shares, codes_ot),
```

durch

```python
            "correlations": results_ot,
```

und setze davor:

```python
    results_ot = correlate_grid(votes_ot, shares, codes_ot)
```

- [ ] **Step 3: Ausgabe der MAUP-Differenzen ergänzen**

Am Ende von `main()` anhängen:

```python
    print(f"\nMAUP — same pairing, Ortsteil (n={len(codes_ot)}) vs Stadtbezirk (n={len(codes_sb)}):")
    for key, cmp in sorted(results["maup"].items(), key=lambda kv: -abs(kv[1]["delta_r"]))[:8]:
        print(
            f"  {key:<28} r={cmp['ortsteil']['r']:+.3f} -> {cmp['stadtbezirk']['r']:+.3f}"
            f"  Δr={cmp['delta_r']:+.3f}"
        )
    print(f"\naggregation validated against {results['validation']['compared']} official figures")
```

- [ ] **Step 4: Laufen lassen**

```bash
cd paper/analysis && ../.venv/bin/python run.py; cd - >/dev/null
```

Erwartet: `n=63`, danach `10` Stadtbezirke, eine MAUP-Tabelle mit Δr-Werten, und `aggregation validated against N official figures` mit N > 0. Bricht es mit „aggregation disagrees" ab, stimmt entweder `parent_code` nicht oder die amtlichen Zeilen betreffen ein anderes Jahr — dann die Abweichung ausdrucken und klären, **nicht** die Prüfung lockern.

- [ ] **Step 5: Commit**

```bash
git add paper/analysis/run.py paper/analysis/results.json
git commit -m "Add the MAUP comparison at Ortsteil and Stadtbezirk level

Election results are official at both levels; the social indicators exist only
per Ortsteil and are summed up via admin_boundaries.parent_code. The sums are
validated against the city's own Stadtbezirk rows — the very rows whose
mis-resolution caused the spatial-key bug now prove the aggregation correct."
```

---

## Task 6: Abbildungen

**Files:**
- Create: `paper/figures/make_figures.py`
- Create: `paper/figures/fig2_choropleth.pdf`, `fig3_scatter.pdf`, `fig4_maup.pdf` (erzeugt)
- Create: `paper/figures/fig1_architecture.pdf` (von Hand gezeichnet)

**Interfaces:**
- Consumes: `paper/analysis/results.json`
- Produces: Vektor-PDFs, eingebunden von `paper/main.tex`

- [ ] **Step 1: dataviz-Skill laden**

**Vor der ersten Chart-Zeile** die `dataviz`-Skill aufrufen. IEEE-Beiträge werden häufig schwarzweiß gedruckt — Farbcodierung allein trägt nicht. Die Skill legt Palette, Achsen und Beschriftung fest; die konkreten Chart-Entscheidungen kommen von dort, nicht aus diesem Plan.

- [ ] **Step 2: Abbildungen erzeugen**

`paper/figures/make_figures.py` schreiben, das aus `results.json` erzeugt:

- **Abb. 2** — Choroplethe des Stimmenanteils je Ortsteil. Geometrien kommen als GeoJSON aus `core.admin_boundaries`; dafür `extract.sh` um eine sechste Abfrage ergänzen (`SELECT code, name, ST_AsGeoJSON(geom) FROM core.admin_boundaries WHERE boundary_type='ortsteil'`) und die Datei `boundaries_geo.csv` nennen.
- **Abb. 3** — Scatter: stärkste Korrelation aus `results["ortsteil"]["correlations"]`, mit Regressionsgerade, r, R² und n in der Ecke.
- **Abb. 4** — Zweipanel: dieselbe Paarung links auf Ortsteil- (n=63), rechts auf Stadtbezirksebene (n=10), beide mit r im Titel.

Alle mit `plt.savefig(..., format="pdf", bbox_inches="tight")`. Schriftgröße mindestens 8 pt, damit sie in einer IEEE-Spalte (8,8 cm) lesbar bleibt.

- [ ] **Step 3: Lesbarkeit in Spaltenbreite prüfen**

```bash
paper/.venv/bin/python -c "
from pypdf import PdfReader
import glob
for f in sorted(glob.glob('paper/figures/*.pdf')):
    box = PdfReader(f).pages[0].mediabox
    print(f'{f}: {float(box.width)/72*2.54:.1f} x {float(box.height)/72*2.54:.1f} cm')
"
```

Jede Abbildung muss auf 8,8 cm Breite skaliert lesbar bleiben. Bei Zweifel als PNG bei 300 dpi rendern und ansehen.

- [ ] **Step 4: Abb. 1 zeichnen**

Die Architekturskizze aus `docs/ARCHITECTURE.md` sauber neu zeichnen — sieben Dienste, Datenfluss von der Quelle bis zum Browser. Als Vektor-PDF nach `paper/figures/fig1_architecture.pdf`.

- [ ] **Step 5: Commit**

```bash
git add paper/figures/ paper/analysis/extract.sh paper/analysis/data/
git commit -m "Generate the paper figures as vector PDFs"
```

---

## Task 7: IEEEtran-Gerüst

**Files:**
- Create: `paper/main.tex`
- Create: `paper/refs.bib`
- Create: `paper/Makefile`

**Interfaces:**
- Consumes: `paper/figures/*.pdf`
- Produces: `paper/main.pdf`

- [ ] **Step 1: refs.bib mit den acht geprüften Quellen anlegen**

Übernimm die verifizierten Angaben aus der Spec, Abschnitt 7. Alle acht wurden am 2026-08-15 gegen die Verlagsseiten geprüft. **Jede weitere Quelle vor Aufnahme prüfen — nichts aus dem Gedächtnis zitieren.**

- [ ] **Step 2: main.tex mit Gerüst und Abschnittsüberschriften anlegen**

```latex
\documentclass[conference]{IEEEtran}
\IEEEoverridecommandlockouts
\usepackage{cite}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{booktabs}
\usepackage{url}
\usepackage[hidelinks]{hyperref}

\begin{document}

\title{Publication Is Not Transparency:\\
Measuring the Distance Between Open Data and Usable Data}

\author{\IEEEauthorblockN{Jonas Paul}
\IEEEauthorblockA{Computational Spatial Humanities\\
Universität Leipzig}
\and
\IEEEauthorblockN{Lucas Berger}
\IEEEauthorblockA{Computational Spatial Humanities\\
Universität Leipzig}}

\maketitle

\begin{abstract}
% 150-200 words, written last.
\end{abstract}

\begin{IEEEkeywords}
open government data, urban dashboards, spatial aggregation, modifiable areal
unit problem, critical data studies
\end{IEEEkeywords}

\section{Introduction}
\section{Background and Related Work}
\section{The Data Landscape and Its Frictions}
\section{System Design}
\section{Results}
\section{Discussion: Transparency and Its Infrastructure}
\section{Limitations and Future Work}
\section{Conclusion}

\bibliographystyle{IEEEtran}
\bibliography{refs}

\end{document}
```

- [ ] **Step 3: Makefile anlegen**

```makefile
PY := .venv/bin/python

.PHONY: all analysis figures paper test clean

all: analysis figures paper

analysis:
	./analysis/extract.sh
	cd analysis && ../$(PY) run.py

figures:
	$(PY) figures/make_figures.py

paper:
	latexmk -pdf -quiet main.tex

test:
	.venv/bin/pytest tests -q

clean:
	latexmk -C
	rm -f main.bbl main.blg
```

- [ ] **Step 4: Bauen und Seitenzahl prüfen**

```bash
cd paper && latexmk -pdf -quiet main.tex && pdfinfo main.pdf | grep Pages; cd - >/dev/null
```

Erwartet: baut ohne Fehler.

- [ ] **Step 5: Commit**

```bash
git add paper/main.tex paper/refs.bib paper/Makefile
git commit -m "Add the IEEEtran skeleton for the paper"
```

---

## Task 8: Text schreiben

**Files:**
- Modify: `paper/main.tex`

**Reihenfolge: III → IV → V → VI → II → VII → VIII → I → Abstract.** Die Einleitung entsteht zuletzt, wenn die Befunde feststehen; das Abstract ganz zum Schluss.

Inhalt, Argumentationsgang und Wortbudget je Abschnitt stehen vollständig in der Spec, Abschnitt 2. Diesen Plan nicht als Ersatz lesen — die Spec ist die Quelle.

- [ ] **Step 1: Abschnitt III schreiben (~600 W. + Tabelle I)**

Tabelle I hat acht Zeilen; Zeilen 7 und 8 sind die stärksten und werden zuletzt gekürzt. Zeile 8 ehrlich rahmen: Die Fehlauflösung war **unser** Bug, ausgelöst durch eine Eigenschaft der Quelle.

- [ ] **Step 2: Abschnitt IV schreiben (~750 W. + Abb. 1)**
- [ ] **Step 3: Abschnitt V schreiben (~700 W. + Tabelle II, Abb. 2–4)**

Jede Zahl aus `results.json` bzw. der Spec, Abschnitt 5. Beide Rückgänge (`geo_features` 4.175.146 → 489.011 und `traffic_restrictions` 30.999 → 1.421) als Deduplizierung ausweisen, nicht als Datenverlust.

- [ ] **Step 4: Abschnitt VI schreiben (~650 W.)**
- [ ] **Step 5: Abschnitt II schreiben (~450 W.)**
- [ ] **Step 6: Abschnitte VII und VIII schreiben (~200 + ~130 W.)**
- [ ] **Step 7: Abschnitt I und Abstract schreiben (~500 W. + 150–200 W.)**
- [ ] **Step 8: Nach jedem Abschnitt bauen und committen**

```bash
cd paper && latexmk -pdf -quiet main.tex && pdfinfo main.pdf | grep Pages; cd - >/dev/null
git add paper/main.tex && git commit -m "Draft section <N>"
```

---

## Task 9: Endprüfung und Übergabe an Lucas

**Files:**
- Modify: `paper/main.tex` (Korrekturen)

- [ ] **Step 1: Seitenzahl prüfen**

```bash
cd paper && pdfinfo main.pdf | grep Pages; cd - >/dev/null
```

Muss **6 oder weniger** sein. Bei Überlauf die Kürzungsreihenfolge aus der Spec, Abschnitt 9, anwenden: erst Abb. 4 in Abb. 3 falten, dann Abschnitt II straffen, dann Tabelle I auf fünf Zeilen. Abschnitte V und VI nicht kürzen.

- [ ] **Step 2: Jede Zahl gegen results.json prüfen**

```bash
grep -oE '[0-9]{1,3}([.,][0-9]{3})+|[0-9]+\.[0-9]+' paper/main.tex | sort -u
```

Jede Zahl in der Ausgabe muss in `paper/analysis/results.json` oder in der Spec, Abschnitt 5, wiederauffindbar sein. Was sich nicht wiederfinden lässt, ist ein Fehler.

- [ ] **Step 3: Tests und vollständigen Build laufen lassen**

```bash
cd paper && make test && make clean && make all; cd - >/dev/null
```

Erwartet: Tests grün, Build ohne Fehler, `main.pdf` neu erzeugt.

- [ ] **Step 4: Auf fehlende Referenzen prüfen**

```bash
grep -c "undefined" paper/main.log || echo "no undefined references"
```

- [ ] **Step 5: Übergabe an Lucas**

`paper/main.pdf` an Lucas geben, mit drei gezielten Fragen statt eines offenen „schau mal drüber":
1. Trägt das Kostenargument in Abschnitt VI, oder wirkt es wie eine Ausrede für die Login-Schranke?
2. Ist die Fallstudie als Methodendemonstration erkennbar, oder liest sie sich als politische Aussage?
3. Fehlt etwas aus der Präsentation, das ins Paper gehört?

- [ ] **Step 6: Rückmeldung einarbeiten und final committen**

```bash
git add paper/ && git commit -m "Apply review feedback from the second author"
```

---

## Selbstprüfung des Plans

**Spec-Abdeckung** — jede Anforderung hat eine Task:

| Spec | Task |
|---|---|
| Abschn. 2, Aufbau I–VIII | 7, 8 |
| Abschn. 3, Fallstudie ew2024 | 3, 4 |
| Abschn. 3, Pflicht-Guard | 1, 3 |
| Abschn. 4, MAUP-Demo | 5 |
| Abschn. 5, Datenstand | 3, 8 |
| Abschn. 6, Abbildungen und Tabellen | 6, 8 |
| Abschn. 7, Zitat-Ökonomie und Literatur | 7 |
| Abschn. 8, Werkzeuge und Arbeitsweise | 2, 7 |
| Abschn. 9, Risiken | 4, 5, 9 |
| Abschn. 10, Resolver-Fix im Scope | 1 |

**Bekannte Lücke:** Tabelle II (Abdeckung vorher/nachher) wird in Task 8 aus der Spec, Abschnitt 5, übernommen und nicht neu erhoben. Die Basislinie vom 2026-06-10 stammt aus `docs/datensatz-analyse.md` und ist nicht reproduzierbar — das ist in Ordnung, muss im Paper aber als Messpunkt mit Datum ausgewiesen werden, nicht als laufende Kennzahl.

**Typkonsistenz:** `metric_key(dataset_id, metric_name)` erzeugt `"<uuid>:<name>"` und wird in `build_counts`, `official_stadtbezirk_counts` und den Modulkonstanten identisch verwendet. `pearson()` liefert überall `{"r","r2","p","n"}`. `parent_of` ist überall `{ortsteil_code: stadtbezirk_code}`.
