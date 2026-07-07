# Korrelationsanalyse v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken correlation scatter plot (categorical x-axis, meaningless Jahr filter, useless Gesamtstadt mode) and add a selectable polynomial trendline (linear/quadratic/cubic) with R².

**Architecture:** Backend `GET /stats/correlation` is reworked to query `core.statistics` directly with two modes — cross-section (join two metrics on canonical `spatial_code` + same `period_year`; auto-picks latest common year) and timeseries (city level, points = years). Frontend gets numeric axes, a year dropdown fed by `available_years` from the response, and a client-side least-squares polynomial fit rendered as a dashed line.

**Tech Stack:** FastAPI + async psycopg3 (backend), React 18 + TypeScript + Recharts 3.8 + react-query v3 (frontend).

**Spec:** `docs/superpowers/specs/2026-07-07-correlation-analysis-v2-design.md`

## Global Constraints

- German UI copy (existing style: „Keine gemeinsamen Daten für diese Kombination", „Punkte = Jahre").
- No new dependencies, no new test framework. Frontend has NO test runner — the regression module is verified via a throwaway `tsx` script in the scratchpad (not committed).
- No local Docker/DB on this machine. SQL is validated against the production DB **read-only** via:
  `ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech "docker exec -i leipzig-data-db-1 psql -U leipzig -d leipzig_data ..."`
- Python 3.11+; match existing code style in `stats_router.py` (inline SQL, `ORJSONResponse`, `@cached`).
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- All work happens on branch `feat/correlation-analysis-v2` (created by the orchestrator before Task 1).
- Scratchpad directory (for throwaway scripts): `/private/tmp/claude-502/-Users-jonaspaul-Documents-Uni-ComputationalSpatialHumanities/8e9c68cf-12a7-4ae9-b604-4b0bba4107ed/scratchpad`

---

### Task 1: Polynomial regression module (`frontend/src/lib/regression.ts`)

Pure math module, no dependencies on other tasks. Parallel-safe with Task 2.

**Files:**
- Create: `frontend/src/lib/regression.ts`
- Verify script (NOT committed): `<scratchpad>/verify-regression.ts`

**Interfaces:**
- Consumes: nothing.
- Produces (Task 3 relies on these exact names/types):
  ```ts
  export interface FitPoint { x: number; y: number }
  export interface PolyFit { degree: number; r2: number; predict: (x: number) => number }
  export function fitPolynomial(points: FitPoint[], degree: number): PolyFit | null
  ```
  Returns `null` when `degree < 1`, `n < degree + 2`, all x identical, y constant, or the normal-equation system is singular.

- [ ] **Step 1: Write the verification script (acts as the failing test)**

Write to `<scratchpad>/verify-regression.ts` (use the scratchpad path from Global Constraints):

```ts
import { fitPolynomial } from "/Users/jonaspaul/Documents/Uni/ComputationalSpatialHumanities/frontend/src/lib/regression";

let failures = 0;
function check(name: string, cond: boolean) {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}`);
  if (!cond) failures++;
}
const approx = (a: number, b: number, eps = 1e-6) => Math.abs(a - b) < eps;

// exakte Rekonstruktion: y = 2x³ − x + 3
const cubic = [-3, -2, -1, 0, 1, 2, 3].map((x) => ({ x, y: 2 * x ** 3 - x + 3 }));
const f3 = fitPolynomial(cubic, 3)!;
check("kubisch: predict(1.5)", approx(f3.predict(1.5), 2 * 1.5 ** 3 - 1.5 + 3));
check("kubisch: r2 = 1", approx(f3.r2, 1, 1e-9));

// linear mit von Hand gerechnetem Fit: slope 0.6, intercept 0.1, r² = 0.9
const lin = [{ x: 0, y: 0 }, { x: 1, y: 1 }, { x: 2, y: 1 }, { x: 3, y: 2 }];
const f1 = fitPolynomial(lin, 1)!;
check("linear: r2 = 0.9", approx(f1.r2, 0.9, 1e-9));
check("linear: predict(0) = 0.1", approx(f1.predict(0), 0.1, 1e-9));
check("linear: predict(3) = 1.9", approx(f1.predict(3), 1.9, 1e-9));

// quadratisch: y = x² exakt, Extrapolation auf x=3
const quad = [-2, -1, 0, 1, 2].map((x) => ({ x, y: x * x }));
const f2 = fitPolynomial(quad, 2)!;
check("quadratisch: predict(3) = 9", approx(f2.predict(3), 9));

// große x-Werte (Zentrierung/Skalierung nötig): y = 0.5x − 1000 um x ≈ 1e6
const big = [0, 1, 2, 3, 4].map((i) => ({ x: 1_000_000 + i * 10, y: 0.5 * (1_000_000 + i * 10) - 1000 }));
const fb = fitPolynomial(big, 1)!;
check("große x: r2 = 1", approx(fb.r2, 1, 1e-6));
check("große x: predict", approx(fb.predict(1_000_025), 0.5 * 1_000_025 - 1000, 1e-3));

// Degenerierte Fälle → null
check("n < degree+2", fitPolynomial(cubic.slice(0, 4), 3) === null);
check("alle x gleich", fitPolynomial([{ x: 1, y: 1 }, { x: 1, y: 2 }, { x: 1, y: 3 }], 1) === null);
check("konstantes y", fitPolynomial([{ x: 0, y: 5 }, { x: 1, y: 5 }, { x: 2, y: 5 }, { x: 3, y: 5 }], 1) === null);
check("degree 0", fitPolynomial(lin, 0) === null);

process.exit(failures ? 1 : 0);
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd /Users/jonaspaul/Documents/Uni/ComputationalSpatialHumanities/frontend && npx -y tsx <scratchpad>/verify-regression.ts`
Expected: FAIL — cannot resolve `.../frontend/src/lib/regression` (module does not exist yet).

- [ ] **Step 3: Implement `frontend/src/lib/regression.ts`**

```ts
export interface FitPoint {
  x: number;
  y: number;
}

export interface PolyFit {
  degree: number;
  r2: number;
  predict: (x: number) => number;
}

/**
 * Polynom-Fit (kleinste Quadrate) über Normalengleichungen. x wird
 * zentriert/skaliert, damit die Gramsche Matrix auch bei großen
 * Achsenwerten (z. B. Einwohnerzahlen) nicht entartet; Lösung per
 * Gauß-Jordan mit Spaltenpivotierung. null bei n < degree + 2,
 * identischen x, konstantem y oder singulärem System.
 */
export function fitPolynomial(points: FitPoint[], degree: number): PolyFit | null {
  const n = points.length;
  if (degree < 1 || n < degree + 2) return null;

  const mx = points.reduce((s, p) => s + p.x, 0) / n;
  const sx = Math.sqrt(points.reduce((s, p) => s + (p.x - mx) ** 2, 0) / n);
  if (sx === 0) return null;
  const ts = points.map((p) => (p.x - mx) / sx);

  const m = degree + 1;
  const pow = new Array(2 * degree + 1).fill(0);
  for (const t of ts) {
    let acc = 1;
    for (let k = 0; k <= 2 * degree; k++) {
      pow[k] += acc;
      acc *= t;
    }
  }
  const A = Array.from({ length: m }, (_, i) =>
    Array.from({ length: m }, (_, j) => pow[i + j])
  );
  const b = new Array(m).fill(0);
  points.forEach((p, idx) => {
    let acc = 1;
    for (let i = 0; i < m; i++) {
      b[i] += p.y * acc;
      acc *= ts[idx];
    }
  });

  const coeffs = solve(A, b);
  if (!coeffs) return null;

  const predict = (x: number) => {
    const t = (x - mx) / sx;
    let y = 0;
    for (let i = degree; i >= 0; i--) y = y * t + coeffs[i];
    return y;
  };

  const my = points.reduce((s, p) => s + p.y, 0) / n;
  const ssTot = points.reduce((s, p) => s + (p.y - my) ** 2, 0);
  if (ssTot === 0) return null;
  const ssRes = points.reduce((s, p) => s + (p.y - predict(p.x)) ** 2, 0);

  return { degree, r2: 1 - ssRes / ssTot, predict };
}

function solve(A: number[][], b: number[]): number[] | null {
  const m = A.length;
  const M = A.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < m; col++) {
    let piv = col;
    for (let r = col + 1; r < m; r++) {
      if (Math.abs(M[r][col]) > Math.abs(M[piv][col])) piv = r;
    }
    if (Math.abs(M[piv][col]) < 1e-10) return null;
    [M[col], M[piv]] = [M[piv], M[col]];
    for (let r = 0; r < m; r++) {
      if (r === col) continue;
      const f = M[r][col] / M[col][col];
      for (let c = col; c <= m; c++) M[r][c] -= f * M[col][c];
    }
  }
  return M.map((row, i) => row[m] / row[i][i]);
}
```

- [ ] **Step 4: Run the verification script — all checks pass**

Run: `cd /Users/jonaspaul/Documents/Uni/ComputationalSpatialHumanities/frontend && npx -y tsx <scratchpad>/verify-regression.ts`
Expected: every line `PASS`, exit code 0.

- [ ] **Step 5: Lint + typecheck the new module**

Run: `cd /Users/jonaspaul/Documents/Uni/ComputationalSpatialHumanities/frontend && npm run lint && npx tsc --noEmit`
Expected: no errors (pre-existing warnings unrelated to `src/lib/regression.ts` are acceptable).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/regression.ts
git commit -m "Add least-squares polynomial fit module for trendlines

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Backend — rework `GET /stats/correlation`

Parallel-safe with Task 1 (different files).

**Files:**
- Modify: `backend/src/api/routers/stats_router.py` (replace the `correlation` endpoint, lines ~124–179; keep `_pearson` as is)

**Interfaces:**
- Consumes: existing `get_conn`, `cached`, `CurrentUser`, `_pearson` from the same file.
- Produces (Task 3 relies on this exact JSON shape):
  ```json
  {
    "metric_a": "...", "metric_b": "...", "spatial_unit": "ortsteil",
    "mode": "cross_section" | "timeseries",
    "year_used": 2019,            // null in timeseries mode or when no data
    "available_years": [2019, 2018],
    "unit_a": "Anzahl",           // null when unknown / no rows
    "unit_b": null,
    "pearson_r": 0.53,            // null when < 2 points or zero variance
    "points": [{"key": "Zentrum", "x": 133, "y": 7010}]
  }
  ```
  Cross-section: `key` = `spatial_key` (display name), one point per `spatial_code`, both values from the SAME `period_year` (= `year_used`; requested `period_year` or latest common year). Timeseries (`spatial_unit == "city"`): `key` = year as string, one point per year, `period_year` param ignored, `year_used` = null, `available_years` = the years that became points (descending).

- [ ] **Step 1: Validate the two SQL queries against the production DB (read-only)**

Cross-section query — expect ~50+ rows (Ortsteile), plausible numeric pairs:

```bash
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech "docker exec -i leipzig-data-db-1 psql -U leipzig -d leipzig_data" <<'SQL'
WITH a AS (
    SELECT DISTINCT ON (spatial_code)
        spatial_code, spatial_key, metric_value, metric_unit
    FROM core.statistics
    WHERE metric_name = 'Apotheken' AND spatial_unit = 'ortsteil'
      AND spatial_code IS NOT NULL AND metric_value IS NOT NULL
      AND period_year = 2019
    ORDER BY spatial_code, period_quarter DESC NULLS LAST,
             period_month DESC NULLS LAST, dataset_id
),
b AS (
    SELECT DISTINCT ON (spatial_code)
        spatial_code, metric_value, metric_unit
    FROM core.statistics
    WHERE metric_name = 'Plätze' AND spatial_unit = 'ortsteil'
      AND spatial_code IS NOT NULL AND metric_value IS NOT NULL
      AND period_year = 2019
    ORDER BY spatial_code, period_quarter DESC NULLS LAST,
             period_month DESC NULLS LAST, dataset_id
)
SELECT count(*) AS n, min(a.metric_value) AS min_a, max(a.metric_value) AS max_a
FROM a JOIN b USING (spatial_code);
SQL
```

Common-years query — expect a descending list of years:

```bash
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech "docker exec -i leipzig-data-db-1 psql -U leipzig -d leipzig_data" <<'SQL'
SELECT period_year FROM core.statistics
WHERE metric_name = 'Apotheken' AND spatial_unit = 'ortsteil'
  AND spatial_code IS NOT NULL AND metric_value IS NOT NULL AND period_year IS NOT NULL
INTERSECT
SELECT period_year FROM core.statistics
WHERE metric_name = 'Plätze' AND spatial_unit = 'ortsteil'
  AND spatial_code IS NOT NULL AND metric_value IS NOT NULL AND period_year IS NOT NULL
ORDER BY period_year DESC;
SQL
```

Timeseries query — pick two metrics that exist at city level first (e.g. via `SELECT metric_name FROM core.statistics WHERE spatial_unit='city' GROUP BY 1 ORDER BY count(DISTINCT period_year) DESC LIMIT 5;`), then run the timeseries CTE below with them and expect one row per common year:

```bash
ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech "docker exec -i leipzig-data-db-1 psql -U leipzig -d leipzig_data" <<'SQL'
WITH a AS (
    SELECT DISTINCT ON (period_year)
        period_year, metric_value, metric_unit
    FROM core.statistics
    WHERE metric_name = '<CITY_METRIC_A>' AND spatial_unit = 'city'
      AND metric_value IS NOT NULL AND period_year IS NOT NULL
    ORDER BY period_year, period_quarter DESC NULLS LAST,
             period_month DESC NULLS LAST, dataset_id
),
b AS (
    SELECT DISTINCT ON (period_year)
        period_year, metric_value, metric_unit
    FROM core.statistics
    WHERE metric_name = '<CITY_METRIC_B>' AND spatial_unit = 'city'
      AND metric_value IS NOT NULL AND period_year IS NOT NULL
    ORDER BY period_year, period_quarter DESC NULLS LAST,
             period_month DESC NULLS LAST, dataset_id
)
SELECT a.period_year, a.metric_value AS value_a, b.metric_value AS value_b
FROM a JOIN b USING (period_year)
ORDER BY a.period_year;
SQL
```

Expected: all three queries run without error and return plausible data. Do NOT run any mutating SQL.

- [ ] **Step 2: Replace the `correlation` endpoint in `stats_router.py`**

Replace the existing `@router.get("/correlation")` function (keep `_pearson` and everything else untouched) with:

```python
_CORR_CROSS_SECTION_SQL = """
WITH a AS (
    SELECT DISTINCT ON (spatial_code)
        spatial_code, spatial_key, metric_value, metric_unit
    FROM core.statistics
    WHERE metric_name = %(metric_a)s
      AND spatial_unit = %(spatial_unit)s
      AND spatial_code IS NOT NULL
      AND metric_value IS NOT NULL
      AND period_year = %(year)s
    ORDER BY spatial_code, period_quarter DESC NULLS LAST,
             period_month DESC NULLS LAST, dataset_id
),
b AS (
    SELECT DISTINCT ON (spatial_code)
        spatial_code, metric_value, metric_unit
    FROM core.statistics
    WHERE metric_name = %(metric_b)s
      AND spatial_unit = %(spatial_unit)s
      AND spatial_code IS NOT NULL
      AND metric_value IS NOT NULL
      AND period_year = %(year)s
    ORDER BY spatial_code, period_quarter DESC NULLS LAST,
             period_month DESC NULLS LAST, dataset_id
)
SELECT a.spatial_key,
       a.metric_value AS value_a, b.metric_value AS value_b,
       a.metric_unit  AS unit_a,  b.metric_unit  AS unit_b
FROM a JOIN b USING (spatial_code)
ORDER BY a.spatial_key
"""

_CORR_COMMON_YEARS_SQL = """
SELECT period_year FROM core.statistics
WHERE metric_name = %(metric_a)s AND spatial_unit = %(spatial_unit)s
  AND spatial_code IS NOT NULL AND metric_value IS NOT NULL
  AND period_year IS NOT NULL
INTERSECT
SELECT period_year FROM core.statistics
WHERE metric_name = %(metric_b)s AND spatial_unit = %(spatial_unit)s
  AND spatial_code IS NOT NULL AND metric_value IS NOT NULL
  AND period_year IS NOT NULL
ORDER BY period_year DESC
"""

_CORR_TIMESERIES_SQL = """
WITH a AS (
    SELECT DISTINCT ON (period_year)
        period_year, metric_value, metric_unit
    FROM core.statistics
    WHERE metric_name = %(metric_a)s AND spatial_unit = 'city'
      AND metric_value IS NOT NULL AND period_year IS NOT NULL
    ORDER BY period_year, period_quarter DESC NULLS LAST,
             period_month DESC NULLS LAST, dataset_id
),
b AS (
    SELECT DISTINCT ON (period_year)
        period_year, metric_value, metric_unit
    FROM core.statistics
    WHERE metric_name = %(metric_b)s AND spatial_unit = 'city'
      AND metric_value IS NOT NULL AND period_year IS NOT NULL
    ORDER BY period_year, period_quarter DESC NULLS LAST,
             period_month DESC NULLS LAST, dataset_id
)
SELECT a.period_year,
       a.metric_value AS value_a, b.metric_value AS value_b,
       a.metric_unit  AS unit_a,  b.metric_unit  AS unit_b
FROM a JOIN b USING (period_year)
ORDER BY a.period_year
"""


@router.get("/correlation")
@cached(ttl=600)
async def correlation(
    _user: CurrentUser,
    metric_a: str,
    metric_b: str,
    spatial_unit: str = Query("ortsteil"),
    period_year: int | None = Query(None),
) -> ORJSONResponse:
    """Pearson-Korrelation zweier Metriken.

    Querschnitt (ortsteil/stadtbezirk/…): paart Werte DESSELBEN Jahres über
    Raumeinheiten, Join auf kanonischem spatial_code; ohne period_year wird
    das neueste gemeinsame Jahr verwendet. Zeitreihe (city): Punkte = Jahre,
    period_year wird ignoriert (eine Gesamtstadt hat pro Jahr genau einen
    Wert — Korrelation ist hier nur über die Zeit sinnvoll).
    """
    params = {"metric_a": metric_a, "metric_b": metric_b, "spatial_unit": spatial_unit}

    async with get_conn() as conn:
        async with conn.cursor() as cur:
            if spatial_unit == "city":
                await cur.execute(_CORR_TIMESERIES_SQL, params)
                rows = await cur.fetchall()
                return _corr_response(
                    params, mode="timeseries", year_used=None,
                    available_years=[r["period_year"] for r in reversed(rows)],
                    rows=rows, key_fn=lambda r: str(r["period_year"]),
                )

            await cur.execute(_CORR_COMMON_YEARS_SQL, params)
            years = [r["period_year"] for r in await cur.fetchall()]
            year_used = period_year if period_year is not None else (years[0] if years else None)
            rows = []
            if year_used is not None:
                await cur.execute(_CORR_CROSS_SECTION_SQL, {**params, "year": year_used})
                rows = await cur.fetchall()
            return _corr_response(
                params, mode="cross_section", year_used=year_used,
                available_years=years, rows=rows,
                key_fn=lambda r: r["spatial_key"],
            )


def _corr_response(params, *, mode, year_used, available_years, rows, key_fn) -> ORJSONResponse:
    xs = [r["value_a"] for r in rows]
    ys = [r["value_b"] for r in rows]
    return ORJSONResponse(
        {
            "metric_a": params["metric_a"],
            "metric_b": params["metric_b"],
            "spatial_unit": params["spatial_unit"],
            "mode": mode,
            "year_used": year_used,
            "available_years": available_years,
            "unit_a": rows[0]["unit_a"] if rows else None,
            "unit_b": rows[0]["unit_b"] if rows else None,
            "pearson_r": _pearson(xs, ys) if rows else None,
            "points": [
                {"key": key_fn(r), "x": r["value_a"], "y": r["value_b"]}
                for r in rows
            ],
        }
    )
```

Note: in timeseries mode `available_years` uses `reversed(rows)` because the SQL orders years ascending but the API contract is descending.

- [ ] **Step 3: Syntax-check**

Run: `python3 -m py_compile /Users/jonaspaul/Documents/Uni/ComputationalSpatialHumanities/backend/src/api/routers/stats_router.py && echo OK`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/src/api/routers/stats_router.py
git commit -m "Rework /stats/correlation: same-year pairing, spatial_code join, city timeseries mode

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend — StatsPanel rework (axes, Jahr dropdown, trendline)

Depends on Task 1 (`fitPolynomial`) and Task 2 (response shape).

**Files:**
- Modify: `frontend/src/api/map.ts` (types + `fetchCorrelation` return type, around line 58)
- Modify: `frontend/src/components/StatsPanel.tsx` (full component rework below)

**Interfaces:**
- Consumes: `fitPolynomial(points, degree): PolyFit | null` from `../lib/regression` (Task 1); correlation JSON shape from Task 2.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add correlation types in `frontend/src/api/map.ts`**

Replace the existing `fetchCorrelation` export with:

```ts
export interface CorrelationPoint {
  key: string;
  x: number;
  y: number;
}
export interface CorrelationResponse {
  metric_a: string;
  metric_b: string;
  spatial_unit: string;
  mode: "cross_section" | "timeseries";
  year_used: number | null;
  available_years: number[];
  unit_a: string | null;
  unit_b: string | null;
  pearson_r: number | null;
  points: CorrelationPoint[];
}

export const fetchCorrelation = (
  metric_a: string,
  metric_b: string,
  spatial_unit = "ortsteil",
  period_year?: number
): Promise<CorrelationResponse> =>
  apiClient
    .get("/stats/correlation", { params: { metric_a, metric_b, spatial_unit, period_year } })
    .then((r) => r.data);
```

- [ ] **Step 2: Rework `frontend/src/components/StatsPanel.tsx`**

Replace the whole file with the version below. It keeps the existing visual language (panel/corners/hud-label classes, color palette, `MetricSelect` with optgroups) and changes: numeric axes, Jahr dropdown (hidden for Gesamtstadt), trend segmented control + dashed fit line, R² readout, n-readout with year, n<3 warning, units in tooltip.

```tsx
import { useMemo, useState } from "react";
import { useQuery } from "react-query";
import { useSearchParams } from "react-router-dom";
import clsx from "clsx";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  CorrelationResponse, fetchCorrelation, fetchGroupedMetrics, MetricGroup,
} from "../api/map";
import { fitPolynomial } from "../lib/regression";

const TREND_OPTIONS = [
  { degree: 0, label: "Aus" },
  { degree: 1, label: "Linear" },
  { degree: 2, label: "Quadratisch" },
  { degree: 3, label: "Kubisch" },
] as const;

const TREND_COLOR = "#ffb02e";

function classify(r: number): { label: string; color: string } {
  const a = Math.abs(r);
  if (a > 0.7) return { label: "Starke Korrelation", color: "#3dd68c" };
  if (a > 0.4) return { label: "Mittlere Korrelation", color: "#ffb02e" };
  return { label: "Schwache Korrelation", color: "#678599" };
}

/** Auswahl über den Indikatoren-Katalog: Optgroups je Thema, kanonische Namen. */
function MetricSelect({
  value,
  onChange,
  groups,
}: {
  value: string;
  onChange: (v: string) => void;
  groups: MetricGroup[];
}) {
  const byTopic = useMemo(() => {
    const map = new Map<string, MetricGroup[]>();
    for (const g of groups) {
      const topic = g.topic ?? "Nicht katalogisiert";
      map.set(topic, [...(map.get(topic) ?? []), g]);
    }
    return [...map.entries()];
  }, [groups]);

  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className="field">
      <option value="">— wählen —</option>
      {byTopic.map(([topic, topicGroups]) => (
        <optgroup key={topic} label={topic}>
          {topicGroups.flatMap((g) =>
            g.metrics.map((m) => (
              <option key={m} value={m}>
                {g.name
                  ? g.metrics.length > 1
                    ? `${g.name} — ${m}`
                    : `${g.name}${g.unit ? ` (${g.unit})` : ""}`
                  : m}
              </option>
            ))
          )}
        </optgroup>
      ))}
    </select>
  );
}

export default function StatsPanel() {
  const [searchParams] = useSearchParams();
  const [metricA, setMetricA] = useState("");
  const [metricB, setMetricB] = useState("");
  const [spatialUnit, setSpatialUnit] = useState("ortsteil");
  const [year, setYear] = useState<number | null>(null);
  const [trendDegree, setTrendDegree] = useState(0);
  const [topicFilter, setTopicFilter] = useState<string | null>(
    searchParams.get("topic")
  );

  const { data: metricGroups = [] } = useQuery<MetricGroup[]>(
    ["metricsGrouped", spatialUnit],
    () => fetchGroupedMetrics(spatialUnit),
    { staleTime: 300_000 }
  );

  const topics = useMemo(
    () =>
      [...new Set(metricGroups.map((g) => g.topic).filter((t): t is string => !!t))].sort(),
    [metricGroups]
  );
  const visibleGroups = useMemo(
    () =>
      topicFilter
        ? metricGroups.filter((g) => g.topic === topicFilter)
        : metricGroups,
    [metricGroups, topicFilter]
  );

  const { data: corrData, isLoading } = useQuery<CorrelationResponse>(
    ["correlation", metricA, metricB, spatialUnit, year],
    () => fetchCorrelation(metricA, metricB, spatialUnit, year ?? undefined),
    { enabled: !!(metricA && metricB), keepPreviousData: true }
  );

  // Jahr ist nur relativ zur Metrik-/Raumebenen-Wahl gültig → bei Wechsel zurücksetzen
  const pickMetricA = (v: string) => { setMetricA(v); setYear(null); };
  const pickMetricB = (v: string) => { setMetricB(v); setYear(null); };
  const pickSpatialUnit = (v: string) => { setSpatialUnit(v); setYear(null); };

  const points = useMemo(() => corrData?.points ?? [], [corrData]);
  const isTimeseries = corrData?.mode === "timeseries";
  const latestYear = corrData?.available_years?.[0] ?? null;

  const fit = useMemo(
    () => (trendDegree > 0 ? fitPolynomial(points, trendDegree) : null),
    [points, trendDegree]
  );
  const trendPoints = useMemo(() => {
    if (!fit || points.length === 0) return [];
    const xs = points.map((p) => p.x);
    const min = Math.min(...xs);
    const max = Math.max(...xs);
    if (min === max) return [];
    return Array.from({ length: 101 }, (_, i) => {
      const x = min + (i * (max - min)) / 100;
      return { x, y: fit.predict(x) };
    });
  }, [fit, points]);

  const nf = useMemo(() => new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 }), []);

  const r: number | null = corrData?.pearson_r ?? null;
  const cls = r != null ? classify(r) : null;
  const nLabel = isTimeseries
    ? "Jahre"
    : spatialUnit === "stadtbezirk"
      ? "Stadtbezirke"
      : "Ortsteile";

  return (
    <div className="blueprint-bg h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-5 p-6 lg:p-8">
        {/* Module header */}
        <header className="animate-rise">
          <p className="hud-label text-signal-cyan">Modul 02 // Analyse</p>
          <h1 className="mt-1 font-display text-2xl font-bold uppercase tracking-[0.12em] text-gotham-100">
            Korrelationsanalyse
          </h1>
          <p className="mt-1 font-mono text-[11px] text-gotham-400">
            Pearson-Korrelation zweier Metriken über Leipziger Raumeinheiten
          </p>
        </header>

        <div className="grid gap-5 lg:grid-cols-12">
          {/* Controls */}
          <section
            className="panel corners h-fit space-y-3.5 p-4 animate-rise lg:col-span-4"
            style={{ animationDelay: "60ms" }}
          >
            <p className="hud-label border-b border-gotham-700 pb-2.5 text-gotham-200">
              Parameter
            </p>

            {/* Themen-Filter aus dem Indikatoren-Katalog */}
            {topics.length > 0 && (
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  onClick={() => setTopicFilter(null)}
                  className={clsx(
                    "border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] transition-colors",
                    topicFilter === null
                      ? "border-signal-cyan bg-signal-cyan/20 text-signal-cyan"
                      : "border-gotham-600 text-gotham-400 hover:border-gotham-400"
                  )}
                >
                  Alle
                </button>
                {topics.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTopicFilter(topicFilter === t ? null : t)}
                    className={clsx(
                      "border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] transition-colors",
                      topicFilter === t
                        ? "border-signal-cyan bg-signal-cyan/20 text-signal-cyan"
                        : "border-gotham-600 text-gotham-400 hover:border-gotham-400"
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}

            <div>
              <label className="hud-label mb-1.5 block">Metrik A — X-Achse</label>
              <MetricSelect value={metricA} onChange={pickMetricA} groups={visibleGroups} />
            </div>

            <div>
              <label className="hud-label mb-1.5 block">Metrik B — Y-Achse</label>
              <MetricSelect value={metricB} onChange={pickMetricB} groups={visibleGroups} />
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="hud-label mb-1.5 block">Raumebene</label>
                <select value={spatialUnit} onChange={(e) => pickSpatialUnit(e.target.value)} className="field">
                  <option value="ortsteil">Ortsteil</option>
                  <option value="stadtbezirk">Stadtbezirk</option>
                  <option value="city">Gesamtstadt</option>
                </select>
              </div>
              <div>
                <label className="hud-label mb-1.5 block">Jahr</label>
                {spatialUnit === "city" ? (
                  <p className="flex h-full items-center font-mono text-[10px] text-gotham-400">
                    Punkte = Jahre
                  </p>
                ) : (
                  <select
                    value={year ?? ""}
                    onChange={(e) => setYear(e.target.value ? parseInt(e.target.value) : null)}
                    className="field"
                    disabled={!corrData}
                  >
                    <option value="">
                      {latestYear != null ? `Neuestes (${latestYear})` : "Neuestes"}
                    </option>
                    {(corrData?.available_years ?? []).map((y) => (
                      <option key={y} value={y}>{y}</option>
                    ))}
                  </select>
                )}
              </div>
            </div>

            {/* Trendlinie */}
            <div>
              <label className="hud-label mb-1.5 block">Trend</label>
              <div className="flex flex-wrap gap-1">
                {TREND_OPTIONS.map((o) => {
                  const insufficient = o.degree > 0 && points.length < o.degree + 2;
                  return (
                    <button
                      key={o.degree}
                      type="button"
                      disabled={insufficient}
                      onClick={() => setTrendDegree(o.degree)}
                      className={clsx(
                        "border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] transition-colors",
                        trendDegree === o.degree
                          ? "border-signal-cyan bg-signal-cyan/20 text-signal-cyan"
                          : "border-gotham-600 text-gotham-400 hover:border-gotham-400",
                        insufficient && "cursor-not-allowed opacity-40 hover:border-gotham-600"
                      )}
                    >
                      {o.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Pearson r readout */}
            {r != null && cls && (
              <div className="border-t border-gotham-700 pt-3.5">
                <p className="hud-label">Pearson r</p>
                <p className="mt-1 font-mono text-3xl font-semibold tracking-tight" style={{ color: cls.color }}>
                  {r > 0 ? "+" : ""}{Number(r).toFixed(3)}
                </p>
                {/* |r| gauge */}
                <div className="mt-2 h-1 w-full bg-gotham-700">
                  <div
                    className="h-full transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.abs(r) * 100)}%`, backgroundColor: cls.color }}
                  />
                </div>
                {points.length < 3 ? (
                  <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: TREND_COLOR }}>
                    n zu klein für belastbare Korrelation
                  </p>
                ) : (
                  <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: cls.color }}>
                    {cls.label}
                  </p>
                )}
                {fit && (
                  <p className="mt-1 font-mono text-[10px] text-gotham-400">
                    R² ({TREND_OPTIONS[trendDegree].label}) = {fit.r2.toFixed(3)}
                  </p>
                )}
                <p className="mt-0.5 font-mono text-[10px] text-gotham-500">
                  n = {points.length} {nLabel}
                  {!isTimeseries && corrData?.year_used != null ? ` (${corrData.year_used})` : ""}
                </p>
              </div>
            )}
          </section>

          {/* Scatter */}
          <section
            className="panel min-h-[420px] p-4 animate-rise lg:col-span-8"
            style={{ animationDelay: "120ms" }}
          >
            <p className="hud-label mb-3 border-b border-gotham-700 pb-2.5 text-gotham-200">
              Streudiagramm
            </p>

            {!metricA || !metricB ? (
              <div className="flex h-80 items-center justify-center">
                <p className="font-mono text-xs text-gotham-500">
                  ▸ Zwei Metriken wählen, um die Analyse zu starten
                </p>
              </div>
            ) : isLoading ? (
              <div className="flex h-80 items-center justify-center">
                <p className="font-mono text-xs text-gotham-400">
                  <span className="led mr-2 inline-block animate-led bg-signal-cyan" />
                  Berechne Korrelation …
                </p>
              </div>
            ) : points.length > 0 ? (
              <div className="h-96">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
                    <CartesianGrid strokeDasharray="2 4" stroke="#1e2e3a" />
                    <XAxis
                      type="number"
                      dataKey="x"
                      name={metricA}
                      domain={["auto", "auto"]}
                      tickFormatter={(v: number) => nf.format(v)}
                      tick={{ fill: "#678599", fontSize: 10, fontFamily: '"IBM Plex Mono", monospace' }}
                      stroke="#2b4253"
                      label={{ value: metricA, position: "insideBottom", offset: -12, fill: "#678599", fontSize: 10 }}
                    />
                    <YAxis
                      type="number"
                      dataKey="y"
                      name={metricB}
                      domain={["auto", "auto"]}
                      tickFormatter={(v: number) => nf.format(v)}
                      tick={{ fill: "#678599", fontSize: 10, fontFamily: '"IBM Plex Mono", monospace' }}
                      stroke="#2b4253"
                      label={{ value: metricB, angle: -90, position: "insideLeft", fill: "#678599", fontSize: 10 }}
                    />
                    <Tooltip
                      cursor={{ stroke: "#53b9e8", strokeDasharray: "3 3" }}
                      content={({ payload }) => {
                        if (!payload?.length) return null;
                        const d = payload[0].payload;
                        if (!d.key) return null; // Trendlinien-Samples haben keinen key
                        return (
                          <div className="panel corners px-3 py-2 font-mono text-[11px]">
                            <p className="mb-1 font-semibold text-gotham-100">{d.key}</p>
                            <p className="text-gotham-300">
                              {metricA}: {nf.format(d.x)}{corrData?.unit_a ? ` ${corrData.unit_a}` : ""}
                            </p>
                            <p className="text-gotham-300">
                              {metricB}: {nf.format(d.y)}{corrData?.unit_b ? ` ${corrData.unit_b}` : ""}
                            </p>
                          </div>
                        );
                      }}
                    />
                    <Scatter data={points} fill="#53b9e8" opacity={0.85} isAnimationActive={false} />
                    {trendPoints.length > 0 && (
                      <Scatter
                        data={trendPoints}
                        line={{ stroke: TREND_COLOR, strokeWidth: 1.5, strokeDasharray: "6 4" }}
                        shape={() => <g />}
                        isAnimationActive={false}
                      />
                    )}
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="flex h-80 items-center justify-center">
                <p className="font-mono text-xs text-gotham-500">
                  Keine gemeinsamen Daten für diese Kombination
                </p>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
```

Notes for the implementer:
- The trend curve is a second `Scatter` whose markers are hidden via `shape={() => <g />}` and whose `line` prop draws the dashed fit — this is the Recharts-3-safe way to overlay a curve in a `ScatterChart`.
- If `npx tsc --noEmit` complains about the `shape` return type, use `shape={() => <g />}` exactly (an empty SVG group element, NOT `null`).
- `keepPreviousData: true` keeps the year dropdown populated while a new year loads.

- [ ] **Step 3: Build + lint**

Run: `cd /Users/jonaspaul/Documents/Uni/ComputationalSpatialHumanities/frontend && npm run build && npm run lint`
Expected: both succeed with no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/map.ts frontend/src/components/StatsPanel.tsx
git commit -m "Correlation scatter: numeric axes, year dropdown, city timeseries mode, polynomial trendline with R²

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: End-to-end verification (orchestrator)

Performed by the orchestrator after Tasks 1–3 are merged into the feature branch — not dispatched to a subagent.

- [ ] Full-tree checks: `npm run build`, `npm run lint`, `python3 -m py_compile backend/src/api/routers/stats_router.py`.
- [ ] Review the combined diff against the spec (`git diff main...feat/correlation-analysis-v2`).
- [ ] Merge to `main` per superpowers:finishing-a-development-branch (push triggers VPS deploy), then verify in the browser on `auerbachs-auge.tech`: numeric x-axis, year dropdown with real years, Gesamtstadt = points-per-year, trendline toggle works, R² shown.
