import { useEffect, useMemo, useState } from "react";
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

  const { data: corrData, isLoading, isPreviousData } = useQuery<CorrelationResponse>(
    ["correlation", metricA, metricB, spatialUnit, year],
    () => fetchCorrelation(metricA, metricB, spatialUnit, year ?? undefined),
    { enabled: !!(metricA && metricB), keepPreviousData: true }
  );

  // Jahr kann durch keepPreviousData für die neue Kombination ungültig sein,
  // solange noch die alten Daten angezeigt werden → nach Refetch reconcilen
  useEffect(() => {
    if (year != null && corrData && !isPreviousData && !corrData.available_years.includes(year)) {
      setYear(null);
    }
  }, [year, corrData, isPreviousData]);

  // Jahr ist nur relativ zur Metrik-/Raumebenen-Wahl gültig → bei Wechsel zurücksetzen
  const pickMetricA = (v: string) => { setMetricA(v); setYear(null); setTrendDegree(0); };
  const pickMetricB = (v: string) => { setMetricB(v); setYear(null); setTrendDegree(0); };
  const pickSpatialUnit = (v: string) => { setSpatialUnit(v); setYear(null); setTrendDegree(0); };

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
              <div className={clsx("h-96 transition-opacity", isPreviousData && "opacity-40")}>
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
