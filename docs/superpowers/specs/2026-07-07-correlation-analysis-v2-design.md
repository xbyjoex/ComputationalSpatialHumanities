# Korrelationsanalyse v2 — Design

**Datum:** 2026-07-07
**Status:** Approved

## Problem

Die Korrelationsanalyse (`/stats`, `StatsPanel.tsx`) hat drei Defekte:

1. **X-Achse kategorial**: Recharts `XAxis` ohne `type="number"` rendert jeden
   x-Wert als eigenen Tick in Datenreihenfolge — das Streudiagramm ist wertlos.
2. **Jahr-Filter kaputt by design**: `GET /stats/correlation` fragt
   `mart.statistics_latest` ab (nur neueste Zeile pro Metrik+Raumeinheit).
   Ein Jahr-Filter leert den Plot oder tut nichts. Zusätzlich erzwingt der
   Join nicht `jahr_A = jahr_B` — Werte verschiedener Jahre werden
   stillschweigend gepaart.
3. **Raumebene „Gesamtstadt" sinnlos**: n=1, Pearson undefiniert.

Nebenbefund: Pearson r wird von Ausreißern (Zentrum) dominiert; eine
Trendlinie macht das sichtbar.

## Lösung

### Backend — `GET /stats/correlation` (Umbau, `stats_router.py`)

Quelle: `core.statistics` statt `mart.statistics_latest`. Zwei Modi:

- **Querschnitt** (`spatial_unit` = `ortsteil` | `stadtbezirk`):
  - Join Metrik A × Metrik B auf **`spatial_code`** (kanonisch, `NOT NULL`)
    und **`a.period_year = b.period_year`**.
  - `period_year`-Param optional; ohne ihn wird das **neueste gemeinsame
    Jahr** beider Metriken verwendet.
  - Duplikate (Quartals-/Monatsdaten, gleiche Metrik in mehreren Datensätzen):
    `DISTINCT ON (spatial_code)` je Metrik mit deterministischer Sortierung
    (`period_quarter DESC NULLS LAST, period_month DESC NULLS LAST,
    dataset_id`).
  - Punkt-`key` = `spatial_key` (Anzeigename).
- **Zeitreihe** (`spatial_unit` = `city`): Punkte = Jahre. Join auf
  `period_year`, ein Wert pro Metrik und Jahr (`DISTINCT ON (period_year)`).
  `period_year`-Param wird ignoriert. Punkt-`key` = Jahr als String.

Response:

```json
{
  "metric_a": "...", "metric_b": "...",
  "spatial_unit": "ortsteil",
  "mode": "cross_section" | "timeseries",
  "year_used": 2024 | null,
  "available_years": [2024, 2023, ...],
  "unit_a": "Anzahl" | null, "unit_b": null,
  "pearson_r": 0.53 | null,
  "points": [{"key": "Zentrum", "x": 133, "y": 7010}]
}
```

`available_years` = Jahre absteigend, in denen **beide** Metriken für die
Raumebene Daten haben (Querschnitt: mit aufgelöstem `spatial_code`;
Zeitreihe: city-Werte). Caching bleibt `@cached(ttl=600)`.

### Frontend — `StatsPanel.tsx`, `api/map.ts`, neu `lib/regression.ts`

1. **Achsen-Fix**: `type="number"` auf X- und Y-Achse, `domain` auto,
   kompakte Tick-Formatierung (`Intl.NumberFormat("de-DE")`).
   `ScatterChart` → `ComposedChart` (Mischung Scatter + Line).
2. **Jahr-Dropdown** statt Zahlenfeld: Optionen aus `available_years`,
   Default-Option „Neuestes (JJJJ)" (`value = null`). Bei Gesamtstadt
   ausgeblendet; stattdessen Hinweis „Punkte = Jahre". Wird ein Jahr
   ungültig (Metrik-Wechsel), fällt die Auswahl auf null zurück.
3. **Trendlinie**: Segmented Control „Trend: Aus / Linear / Quadratisch /
   Kubisch". `fitPolynomial(points, degree)` in `lib/regression.ts`:
   kleinste Quadrate über Normalengleichungen mit x-Zentrierung/Skalierung
   (numerische Stabilität), Gauß-Elimination; Rückgabe
   `{ predict(x), r2 }` oder `null` (singulär oder `n < degree + 2`).
   Kurve: ~100 Samples über `[xmin, xmax]`, gestrichelte `Line`
   (`dot=false`) im ComposedChart. R² im Parameter-Panel unter Pearson r
   („R² (kubisch) = 0.87").
4. **Readouts**: „n = 53 Ortsteile (2024)" bzw. „n = 10 Jahre";
   Tooltip zeigt Einheiten (`unit_a`/`unit_b`).

### Fehlerfälle

- Keine gemeinsamen Jahre/Punkte → „Keine gemeinsamen Daten für diese
  Kombination".
- `n < degree + 2` oder singulärer Fit → Trend-Grad-Button disabled bzw.
  Linie/R² ausgeblendet.
- `n < 3` → Warnhinweis „n zu klein für belastbare Korrelation" statt
  Klassifikationslabel (Stark/Mittel/Schwach).

## Verifikation

- SQL-Queries gegen die VPS-DB testen (`ssh deploy@auerbachs-auge.tech`,
  psql im Container `leipzig-data-db-1`).
- Backend: Import-/Lint-Check im lokalen venv; kein DB-Test-Harness
  vorhanden.
- Frontend: `npm run build` + `npm run lint`.
- `fitPolynomial`: Wegwerf-Verifikationsskript im Scratchpad gegen bekannte
  Polynome (kein Test-Runner im Frontend; wird nicht neu eingeführt).

## Nicht im Scope

Spearman-Rangkorrelation, Log-Skalen-Toggles, Backend-Fit.
