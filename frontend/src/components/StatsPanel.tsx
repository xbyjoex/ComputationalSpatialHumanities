import { useState } from "react";
import { useQuery } from "react-query";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  LineChart, Line, ResponsiveContainer, Legend,
} from "recharts";
import { fetchCorrelation, fetchMetrics } from "../api/map";
import { TrendingUp } from "lucide-react";

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

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div className="flex items-center gap-3">
        <TrendingUp className="w-5 h-5 text-brand-400" />
        <h1 className="text-xl font-bold text-white">Statistiken & Korrelationen</h1>
      </div>

      {/* Correlation controls */}
      <div className="bg-slate-800 border border-slate-700 rounded-2xl p-5 space-y-4">
        <h2 className="text-sm font-semibold text-slate-300">Korrelationsanalyse</h2>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Metrik A (X-Achse)</label>
            <select
              value={metricA}
              onChange={(e) => setMetricA(e.target.value)}
              className="w-full bg-slate-700 text-slate-200 text-sm rounded-lg px-2 py-1.5 border border-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="">— wählen —</option>
              {metrics.map((m: string) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Metrik B (Y-Achse)</label>
            <select
              value={metricB}
              onChange={(e) => setMetricB(e.target.value)}
              className="w-full bg-slate-700 text-slate-200 text-sm rounded-lg px-2 py-1.5 border border-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="">— wählen —</option>
              {metrics.map((m: string) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Raumebene</label>
            <select
              value={spatialUnit}
              onChange={(e) => setSpatialUnit(e.target.value)}
              className="w-full bg-slate-700 text-slate-200 text-sm rounded-lg px-2 py-1.5 border border-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="ortsteil">Ortsteil</option>
              <option value="stadtbezirk">Stadtbezirk</option>
              <option value="city">Gesamtstadt</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Jahr</label>
            <input
              type="number"
              value={year ?? ""}
              onChange={(e) => setYear(e.target.value ? parseInt(e.target.value) : null)}
              placeholder="alle"
              className="w-full bg-slate-700 text-slate-200 text-sm rounded-lg px-2 py-1.5 border border-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>
        </div>

        {/* Pearson r badge */}
        {corrData?.pearson_r != null && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Pearson r:</span>
            <span
              className={`text-sm font-bold px-2 py-0.5 rounded-full ${
                Math.abs(corrData.pearson_r) > 0.7
                  ? "bg-green-900 text-green-300"
                  : Math.abs(corrData.pearson_r) > 0.4
                  ? "bg-yellow-900 text-yellow-300"
                  : "bg-slate-700 text-slate-300"
              }`}
            >
              {corrData.pearson_r}
            </span>
            <span className="text-xs text-slate-500">({corrData.points?.length} Einheiten)</span>
          </div>
        )}

        {/* Scatter plot */}
        {corrData?.points?.length > 0 && (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  dataKey="x"
                  name={metricA}
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  label={{ value: metricA, position: "insideBottom", offset: -4, fill: "#94a3b8", fontSize: 11 }}
                />
                <YAxis
                  dataKey="y"
                  name={metricB}
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  label={{ value: metricB, angle: -90, position: "insideLeft", fill: "#94a3b8", fontSize: 11 }}
                />
                <Tooltip
                  cursor={{ strokeDasharray: "3 3" }}
                  content={({ payload }) => {
                    if (!payload?.length) return null;
                    const d = payload[0].payload;
                    return (
                      <div className="bg-slate-700 border border-slate-600 rounded-lg p-2 text-xs">
                        <p className="font-semibold text-white mb-1">{d.key}</p>
                        <p className="text-slate-300">{metricA}: {d.x}</p>
                        <p className="text-slate-300">{metricB}: {d.y}</p>
                      </div>
                    );
                  }}
                />
                <Scatter
                  data={corrData.points}
                  fill="#3b82f6"
                  opacity={0.8}
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        )}

        {isLoading && (
          <p className="text-slate-500 text-sm text-center py-4">Lade Daten …</p>
        )}
        {!isLoading && metricA && metricB && corrData?.points?.length === 0 && (
          <p className="text-slate-500 text-sm text-center py-4">Keine Daten für diese Kombination</p>
        )}
      </div>
    </div>
  );
}
