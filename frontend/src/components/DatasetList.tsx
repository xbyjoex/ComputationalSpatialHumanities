import { useState } from "react";
import { useQuery } from "react-query";
import { fetchDatasets, fetchDatasetStatus } from "../api/map";
import { Database, CheckCircle, XCircle, Clock, Wifi, WifiOff } from "lucide-react";
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

export default function DatasetList() {
  const [search, setSearch] = useState("");
  const [scheduleFilter, setScheduleFilter] = useState<"" | "nightly" | "live">("");

  const { data: statusData = [], isLoading } = useQuery<StatusRow[]>(
    "datasetStatus",
    fetchDatasetStatus,
    { refetchInterval: 60_000, staleTime: 30_000 }
  );

  const filtered = statusData.filter((d) => {
    if (scheduleFilter && d.schedule !== scheduleFilter) return false;
    if (search && !d.title.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const statusIcon = (s: string | null) => {
    if (s === "success") return <CheckCircle className="w-3.5 h-3.5 text-green-400" />;
    if (s === "failed") return <XCircle className="w-3.5 h-3.5 text-red-400" />;
    if (s === "started") return <Clock className="w-3.5 h-3.5 text-yellow-400 animate-spin" />;
    return <span className="w-3.5 h-3.5 rounded-full bg-slate-600 inline-block" />;
  };

  return (
    <div className="h-full overflow-y-auto p-6 space-y-4">
      <div className="flex items-center gap-3">
        <Database className="w-5 h-5 text-brand-400" />
        <h1 className="text-xl font-bold text-white">Datensätze</h1>
        <span className="ml-auto text-xs text-slate-500">{filtered.length} / {statusData.length}</span>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <input
          type="search"
          placeholder="Suche …"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <select
          value={scheduleFilter}
          onChange={(e) => setScheduleFilter(e.target.value as typeof scheduleFilter)}
          className="bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">Alle</option>
          <option value="live">Live</option>
          <option value="nightly">Nightly</option>
        </select>
      </div>

      {/* Table */}
      {isLoading ? (
        <p className="text-slate-500 text-sm text-center py-8">Lade Datensätze …</p>
      ) : (
        <div className="space-y-1.5">
          {filtered.map((d) => (
            <div
              key={d.id}
              className="bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 flex items-center gap-4 hover:border-slate-500 transition"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white font-medium truncate">{d.title}</p>
                <div className="flex items-center gap-3 mt-0.5">
                  <span className={clsx(
                    "flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full",
                    d.schedule === "live"
                      ? "bg-green-900/50 text-green-400"
                      : "bg-slate-700 text-slate-400"
                  )}>
                    {d.schedule === "live" ? <Wifi className="w-2.5 h-2.5" /> : <WifiOff className="w-2.5 h-2.5" />}
                    {d.schedule}
                  </span>
                  {d.best_format && (
                    <span className="text-[10px] text-slate-500">{d.best_format}</span>
                  )}
                  {d.has_geo && (
                    <span className="text-[10px] text-blue-400">GEO</span>
                  )}
                </div>
              </div>

              {/* Last run info */}
              <div className="flex items-center gap-2 shrink-0 text-xs text-slate-500">
                {statusIcon(d.last_run_status)}
                {d.last_run_at ? (
                  <span>
                    {formatDistanceToNow(new Date(d.last_run_at), { locale: de, addSuffix: true })}
                  </span>
                ) : (
                  <span>nie</span>
                )}
                {d.last_run_rows != null && (
                  <span className="text-slate-600">· {d.last_run_rows.toLocaleString()} Zeilen</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
