import { useEffect, useState } from "react";
import { useQuery } from "react-query";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { X, ChevronDown, ChevronUp } from "lucide-react";
import { useMapStore, DockItem } from "../store/mapStore";
import { fetchMetrics } from "../api/map";
import { fetchTimeseries } from "../api/map";

/**
 * Bottom dock for non-geo statistics — datasets that have no spatial breakdown
 * and therefore cannot be a choropleth. Each pinned dataset becomes a chart:
 * a line for time series, a bar chart for single-period distributions.
 */
export default function ContextDock() {
  const { dockItems } = useMapStore();
  const [open, setOpen] = useState(true);
  if (dockItems.length === 0) return null;

  return (
    <div className="absolute bottom-5 left-1/2 z-10 w-[min(880px,calc(100vw-2.5rem))] -translate-x-1/2 animate-rise">
      <div className="panel corners">
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-2.5 border-b border-gotham-700 px-3.5 py-2 text-left transition-colors hover:bg-gotham-800"
        >
          <span className="led animate-led bg-signal-amber" />
          <span className="hud-label text-gotham-200">Kontext · Statistik</span>
          <span className="ml-auto font-mono text-[10px] text-gotham-500">
            {dockItems.length}
          </span>
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 text-gotham-500" />
          ) : (
            <ChevronUp className="h-3.5 w-3.5 text-gotham-500" />
          )}
        </button>
        {open && (
          <div className="flex gap-3 overflow-x-auto px-3 py-3">
            {dockItems.map((item) => (
              <DockCard key={item.datasetId} item={item} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DockCard({ item }: { item: DockItem }) {
  const { removeDockItem } = useMapStore();
  const [metric, setMetric] = useState<string>("");

  const { data: metrics = [] } = useQuery<string[]>(
    ["cityMetrics", item.datasetId],
    () => fetchMetrics("city", item.datasetId),
    { staleTime: 300_000 }
  );

  useEffect(() => {
    if (metrics.length && !metrics.includes(metric)) setMetric(metrics[0]);
  }, [metrics, metric]);

  const { data: ts } = useQuery(
    ["timeseries", item.datasetId, metric],
    () => fetchTimeseries(item.datasetId, metric),
    { enabled: !!metric, staleTime: 300_000 }
  );

  const series = (ts?.series ?? []).filter((p) => p.value != null);
  const isTimeline = item.kind === "timeseries" && series.length > 1;
  const data = series.map((p) => ({
    label: p.year ? String(p.year) : p.period,
    value: p.value as number,
  }));
  const unit = series[0]?.unit;

  return (
    <div className="flex w-[300px] shrink-0 flex-col border border-gotham-700 bg-gotham-900/60">
      <div className="flex items-start gap-2 border-b border-gotham-800 px-2.5 py-1.5">
        <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-gotham-100" title={item.title}>
          {item.title}
        </span>
        <button
          onClick={() => removeDockItem(item.datasetId)}
          className="shrink-0 text-gotham-500 transition-colors hover:text-signal-red"
        >
          <X className="h-3 w-3" />
        </button>
      </div>

      {metrics.length > 1 && (
        <select
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
          className="field m-2 mb-0 !py-1 text-[10px]"
        >
          {metrics.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      )}

      <div className="h-32 px-1 py-2">
        {data.length === 0 ? (
          <p className="flex h-full items-center justify-center font-mono text-[10px] text-gotham-500">
            {metric ? "keine Werte" : "lade …"}
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            {isTimeline ? (
              <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
                <CartesianGrid stroke="#1b2832" strokeDasharray="2 3" />
                <XAxis dataKey="label" tick={{ fill: "#5b7186", fontSize: 9 }} tickLine={false} />
                <YAxis tick={{ fill: "#5b7186", fontSize: 9 }} tickLine={false} width={42} />
                <Tooltip
                  contentStyle={{ background: "#0a1015", border: "1px solid #2b4253", fontSize: 11 }}
                  labelStyle={{ color: "#9fb3c4" }}
                />
                <Line type="monotone" dataKey="value" stroke="#53b9e8" strokeWidth={1.6} dot={false} />
              </LineChart>
            ) : (
              <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
                <CartesianGrid stroke="#1b2832" strokeDasharray="2 3" />
                <XAxis dataKey="label" tick={{ fill: "#5b7186", fontSize: 9 }} tickLine={false} />
                <YAxis tick={{ fill: "#5b7186", fontSize: 9 }} tickLine={false} width={42} />
                <Tooltip
                  contentStyle={{ background: "#0a1015", border: "1px solid #2b4253", fontSize: 11 }}
                  labelStyle={{ color: "#9fb3c4" }}
                  cursor={{ fill: "#14202a" }}
                />
                <Bar dataKey="value" fill="#53b9e8" />
              </BarChart>
            )}
          </ResponsiveContainer>
        )}
      </div>
      {unit && (
        <p className="px-2.5 pb-1.5 font-mono text-[9px] text-gotham-500">Einheit: {unit}</p>
      )}
    </div>
  );
}
