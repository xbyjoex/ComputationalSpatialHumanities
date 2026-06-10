import { useState } from "react";
import { useQuery } from "react-query";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import { fetchCorrelation, fetchMetrics } from "../api/map";

function classify(r: number): { label: string; color: string } {
  const a = Math.abs(r);
  if (a > 0.7) return { label: "Starke Korrelation", color: "#3dd68c" };
  if (a > 0.4) return { label: "Mittlere Korrelation", color: "#ffb02e" };
  return { label: "Schwache Korrelation", color: "#678599" };
}

export default function StatsPanel() {
  const [metricA, setMetricA] = useState("");
  const [metricB, setMetricB] = useState("");
  const [spatialUnit, setSpatialUnit] = useState("ortsteil");
  const [year, setYear] = useState<number | null>(null);

  const { data: metrics = [] } = useQuery<string[]>("metrics", () => fetchMetrics(), {
    staleTime: 300_000,
  });

  const { data: corrData, isLoading } = useQuery(
    ["correlation", metricA, metricB, spatialUnit, year],
    () => fetchCorrelation(metricA, metricB, spatialUnit, year ?? undefined),
    { enabled: !!(metricA && metricB) }
  );

  const r: number | null = corrData?.pearson_r ?? null;
  const cls = r != null ? classify(r) : null;

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

            <div>
              <label className="hud-label mb-1.5 block">Metrik A — X-Achse</label>
              <select value={metricA} onChange={(e) => setMetricA(e.target.value)} className="field">
                <option value="">— wählen —</option>
                {metrics.map((m: string) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>

            <div>
              <label className="hud-label mb-1.5 block">Metrik B — Y-Achse</label>
              <select value={metricB} onChange={(e) => setMetricB(e.target.value)} className="field">
                <option value="">— wählen —</option>
                {metrics.map((m: string) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label className="hud-label mb-1.5 block">Raumebene</label>
                <select value={spatialUnit} onChange={(e) => setSpatialUnit(e.target.value)} className="field">
                  <option value="ortsteil">Ortsteil</option>
                  <option value="stadtbezirk">Stadtbezirk</option>
                  <option value="city">Gesamtstadt</option>
                </select>
              </div>
              <div>
                <label className="hud-label mb-1.5 block">Jahr</label>
                <input
                  type="number"
                  value={year ?? ""}
                  onChange={(e) => setYear(e.target.value ? parseInt(e.target.value) : null)}
                  placeholder="alle"
                  className="field"
                />
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
                <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: cls.color }}>
                  {cls.label}
                </p>
                <p className="mt-0.5 font-mono text-[10px] text-gotham-500">
                  n = {corrData.points?.length} Raumeinheiten
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
            ) : corrData?.points?.length > 0 ? (
              <div className="h-96">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
                    <CartesianGrid strokeDasharray="2 4" stroke="#1e2e3a" />
                    <XAxis
                      dataKey="x"
                      name={metricA}
                      tick={{ fill: "#678599", fontSize: 10, fontFamily: '"IBM Plex Mono", monospace' }}
                      stroke="#2b4253"
                      label={{ value: metricA, position: "insideBottom", offset: -12, fill: "#678599", fontSize: 10 }}
                    />
                    <YAxis
                      dataKey="y"
                      name={metricB}
                      tick={{ fill: "#678599", fontSize: 10, fontFamily: '"IBM Plex Mono", monospace' }}
                      stroke="#2b4253"
                      label={{ value: metricB, angle: -90, position: "insideLeft", fill: "#678599", fontSize: 10 }}
                    />
                    <Tooltip
                      cursor={{ stroke: "#53b9e8", strokeDasharray: "3 3" }}
                      content={({ payload }) => {
                        if (!payload?.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="panel corners px-3 py-2 font-mono text-[11px]">
                            <p className="mb-1 font-semibold text-gotham-100">{d.key}</p>
                            <p className="text-gotham-300">{metricA}: {d.x}</p>
                            <p className="text-gotham-300">{metricB}: {d.y}</p>
                          </div>
                        );
                      }}
                    />
                    <Scatter data={corrData.points} fill="#53b9e8" opacity={0.85} />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="flex h-80 items-center justify-center">
                <p className="font-mono text-xs text-gotham-500">
                  Keine Daten für diese Kombination
                </p>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
