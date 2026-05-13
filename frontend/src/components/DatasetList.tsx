import { useState } from "react";
import { useQuery } from "react-query";
import { Link } from "react-router-dom";
import { fetchDatasetStatus } from "../api/map";
import { getDataset, getDatasetStats } from "../api/datasets";
import {
  Database,
  CheckCircle,
  XCircle,
  Clock,
  Wifi,
  WifiOff,
  ChevronDown,
  ChevronRight,
  ExternalLink,
} from "lucide-react";
import clsx from "clsx";
import { formatDistanceToNow } from "date-fns";
import { de } from "date-fns/locale";

type StatusRow = {
  id: string;
  title: string;
  schedule: string;
  has_geo: boolean;
  best_format: string | null;
  last_ingested: string | null;
  last_run_status: string | null;
  last_run_at: string | null;
  last_run_rows: number | null;
};

function statusIcon(s: string | null) {
  if (s === "success") return <CheckCircle className="w-3.5 h-3.5 text-green-400" />;
  if (s === "failed") return <XCircle className="w-3.5 h-3.5 text-red-400" />;
  if (s === "started") return <Clock className="w-3.5 h-3.5 text-yellow-400 animate-spin" />;
  return <span className="w-3.5 h-3.5 rounded-full bg-slate-600 inline-block" />;
}

function ExpandedPanel({ datasetId }: { datasetId: string }) {
  const { data: detail, isLoading: dLoading } = useQuery(
    ["dataset", datasetId],
    () => getDataset(datasetId),
    { staleTime: 60_000 }
  );
  const { data: stats, isLoading: sLoading } = useQuery(
    ["dataset-stats", datasetId],
    () => getDatasetStats(datasetId),
    { staleTime: 60_000 }
  );

  if (dLoading || sLoading) {
    return <p className="text-xs text-slate-500 px-4 py-3">Lade …</p>;
  }
  if (!detail) return null;

  const ds = detail.dataset;
  return (
    <div className="px-4 py-3 border-t border-slate-700 bg-slate-900/50 space-y-3 text-xs">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-300">
        <div><span className="text-slate-500">ID:</span> <code className="text-slate-200">{ds.id}</code></div>
        <div>
          <span className="text-slate-500">Zeilen in DB:</span>{" "}
          <span className="text-slate-100 font-semibold">{detail.row_count.toLocaleString()}</span>
        </div>
        <div><span className="text-slate-500">Tabelle:</span> <code>{detail.target_table ?? "–"}</code></div>
        <div><span className="text-slate-500">Formate:</span> {(ds.formats ?? []).join(", ") || "–"}</div>
        {ds.best_url && (
          <div className="col-span-2 truncate">
            <span className="text-slate-500">Quelle:</span>{" "}
            <a
              href={ds.best_url}
              target="_blank"
              rel="noreferrer"
              className="text-brand-400 hover:underline inline-flex items-center gap-1"
            >
              {ds.best_url} <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        )}
      </div>

      {stats && stats.target_table && (
        <StatsSummary stats={stats} />
      )}

      <div className="flex justify-end">
        <Link
          to={`/datasets/${encodeURIComponent(datasetId)}`}
          className="inline-flex items-center gap-1 text-brand-400 hover:text-brand-300 hover:underline"
        >
          Details & Daten öffnen <ChevronRight className="w-3 h-3" />
        </Link>
      </div>
    </div>
  );
}

function StatsSummary({ stats }: { stats: NonNullable<Awaited<ReturnType<typeof getDatasetStats>>> }) {
  const buckets =
    stats.per_metric ?? stats.per_type ?? stats.per_site ?? stats.per_counter ?? [];
  if (buckets.length === 0) {
    return <p className="text-slate-500">Keine Statistik verfügbar.</p>;
  }
  const keys = Object.keys(buckets[0]);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-slate-500 border-b border-slate-700">
            {keys.map((k) => (
              <th key={k} className="text-left font-medium py-1 pr-3">{k}</th>
            ))}
          </tr>
        </thead>
        <tbody className="text-slate-200">
          {buckets.slice(0, 8).map((row, i) => (
            <tr key={i} className="border-b border-slate-800 last:border-0">
              {keys.map((k) => (
                <td key={k} className="py-1 pr-3 truncate max-w-[160px]">
                  {formatValue(row[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {buckets.length > 8 && (
        <p className="text-slate-600 mt-1">… und {buckets.length - 8} weitere</p>
      )}
    </div>
  );
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return String(v);
    return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
  }
  return String(v);
}

export default function DatasetList() {
  const [search, setSearch] = useState("");
  const [scheduleFilter, setScheduleFilter] = useState<"" | "nightly" | "live">("");
  const [geoFilter, setGeoFilter] = useState<"" | "geo" | "nogeo">("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data: statusData = [], isLoading } = useQuery<StatusRow[]>(
    "datasetStatus",
    fetchDatasetStatus,
    { refetchInterval: 60_000, staleTime: 30_000 }
  );

  const filtered = statusData.filter((d) => {
    if (scheduleFilter && d.schedule !== scheduleFilter) return false;
    if (geoFilter === "geo" && !d.has_geo) return false;
    if (geoFilter === "nogeo" && d.has_geo) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!d.title.toLowerCase().includes(q) && !d.id.toLowerCase().includes(q)) {
        return false;
      }
    }
    return true;
  });

  return (
    <div className="h-full overflow-y-auto p-6 space-y-4">
      <div className="flex items-center gap-3">
        <Database className="w-5 h-5 text-brand-400" />
        <h1 className="text-xl font-bold text-white">Datensätze</h1>
        <span className="ml-auto text-xs text-slate-500">
          {filtered.length} / {statusData.length}
        </span>
      </div>

      <div className="flex gap-3 flex-wrap">
        <input
          type="search"
          placeholder="Suche (Titel oder ID) …"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[200px] bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <select
          value={scheduleFilter}
          onChange={(e) => setScheduleFilter(e.target.value as typeof scheduleFilter)}
          className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">Alle Zeitpläne</option>
          <option value="live">Live</option>
          <option value="nightly">Nightly</option>
        </select>
        <select
          value={geoFilter}
          onChange={(e) => setGeoFilter(e.target.value as typeof geoFilter)}
          className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">Alle</option>
          <option value="geo">Mit Geo</option>
          <option value="nogeo">Ohne Geo</option>
        </select>
      </div>

      {isLoading ? (
        <p className="text-slate-500 text-sm text-center py-8">Lade Datensätze …</p>
      ) : (
        <div className="space-y-1.5">
          {filtered.map((d) => {
            const isOpen = expanded === d.id;
            return (
              <div
                key={d.id}
                className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden hover:border-slate-500 transition"
              >
                <button
                  type="button"
                  onClick={() => setExpanded(isOpen ? null : d.id)}
                  className="w-full px-4 py-3 flex items-center gap-4 text-left"
                >
                  {isOpen ? (
                    <ChevronDown className="w-4 h-4 text-slate-500 shrink-0" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-slate-500 shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white font-medium truncate">{d.title}</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span
                        className={clsx(
                          "flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full",
                          d.schedule === "live"
                            ? "bg-green-900/50 text-green-400"
                            : "bg-slate-700 text-slate-400"
                        )}
                      >
                        {d.schedule === "live" ? (
                          <Wifi className="w-2.5 h-2.5" />
                        ) : (
                          <WifiOff className="w-2.5 h-2.5" />
                        )}
                        {d.schedule}
                      </span>
                      {d.best_format && (
                        <span className="text-[10px] text-slate-500">{d.best_format}</span>
                      )}
                      {d.has_geo && <span className="text-[10px] text-blue-400">GEO</span>}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 text-xs text-slate-500">
                    {statusIcon(d.last_run_status)}
                    {d.last_run_at ? (
                      <span>
                        {formatDistanceToNow(new Date(d.last_run_at), {
                          locale: de,
                          addSuffix: true,
                        })}
                      </span>
                    ) : (
                      <span>nie</span>
                    )}
                    {d.last_run_rows != null && (
                      <span className="text-slate-600">
                        · {d.last_run_rows.toLocaleString()} Zeilen
                      </span>
                    )}
                  </div>
                </button>

                {isOpen && <ExpandedPanel datasetId={d.id} />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
