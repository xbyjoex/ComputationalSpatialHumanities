import { useState } from "react";
import { useQuery } from "react-query";
import { Link } from "react-router-dom";
import { fetchDatasetStatus } from "../api/map";
import { getDataset, getDatasetStats } from "../api/datasets";
import {
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

function StatusLed({ s }: { s: string | null }) {
  if (s === "success") return <span className="led bg-signal-green" title="Erfolgreich" />;
  if (s === "failed") return <span className="led bg-signal-red" title="Fehlgeschlagen" />;
  if (s === "started") return <span className="led animate-led bg-signal-amber" title="Läuft" />;
  if (s === "skipped") return <span className="led bg-gotham-400" title="Übersprungen — Quelle unverändert" />;
  return <span className="led bg-gotham-600" title="Kein Lauf" />;
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
    return <p className="px-4 py-3 font-mono text-[11px] text-gotham-500">Lade …</p>;
  }
  if (!detail) return null;

  const ds = detail.dataset;
  return (
    <div className="space-y-3 border-t border-gotham-700 bg-gotham-900/70 px-4 py-3 font-mono text-[11px]">
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-gotham-300">
        <div>
          <span className="text-gotham-500">ID&nbsp;&nbsp;</span>
          <code className="text-gotham-200">{ds.id}</code>
        </div>
        <div>
          <span className="text-gotham-500">Zeilen in DB&nbsp;&nbsp;</span>
          <span className="font-semibold text-signal-bright">{detail.row_count.toLocaleString()}</span>
        </div>
        <div>
          <span className="text-gotham-500">Tabelle&nbsp;&nbsp;</span>
          <code>{detail.target_table ?? "–"}</code>
        </div>
        <div>
          <span className="text-gotham-500">Formate&nbsp;&nbsp;</span>
          {(ds.formats ?? []).join(", ") || "–"}
        </div>
        {ds.best_url && (
          <div className="col-span-2 truncate">
            <span className="text-gotham-500">Quelle&nbsp;&nbsp;</span>
            <a
              href={ds.best_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-signal-cyan hover:text-signal-bright hover:underline"
            >
              {ds.best_url} <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        )}
      </div>

      {stats && stats.target_table && <StatsSummary stats={stats} />}

      <div className="flex justify-end">
        <Link
          to={`/datasets/${encodeURIComponent(datasetId)}`}
          className="inline-flex items-center gap-1 uppercase tracking-[0.12em] text-signal-cyan hover:text-signal-bright"
        >
          Details &amp; Daten öffnen <ChevronRight className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
}

function StatsSummary({ stats }: { stats: NonNullable<Awaited<ReturnType<typeof getDatasetStats>>> }) {
  const buckets =
    stats.per_metric ?? stats.per_type ?? stats.per_site ?? stats.per_counter ?? [];
  if (buckets.length === 0) {
    return <p className="text-gotham-500">Keine Statistik verfügbar.</p>;
  }
  const keys = Object.keys(buckets[0]);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="border-b border-gotham-700 text-gotham-500">
            {keys.map((k) => (
              <th key={k} className="py-1 pr-3 text-left font-medium uppercase tracking-[0.1em]">{k}</th>
            ))}
          </tr>
        </thead>
        <tbody className="text-gotham-200">
          {buckets.slice(0, 8).map((row, i) => (
            <tr key={i} className="border-b border-gotham-750 last:border-0">
              {keys.map((k) => (
                <td key={k} className="max-w-[160px] truncate py-1 pr-3">
                  {formatValue(row[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {buckets.length > 8 && (
        <p className="mt-1 text-gotham-500">… und {buckets.length - 8} weitere</p>
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
    <div className="blueprint-bg h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-5 p-6 lg:p-8">
        {/* Module header */}
        <header className="flex items-end justify-between animate-rise">
          <div>
            <p className="hud-label text-signal-cyan">Modul 03 // Datenbestand</p>
            <h1 className="mt-1 font-display text-2xl font-bold uppercase tracking-[0.12em] text-gotham-100">
              Quellenregister
            </h1>
          </div>
          <p className="font-mono text-[11px] text-gotham-400">
            <span className="text-signal-bright">{filtered.length}</span>
            <span className="text-gotham-500"> / {statusData.length} Quellen</span>
          </p>
        </header>

        {/* Filters */}
        <div className="flex flex-wrap gap-2.5 animate-rise" style={{ animationDelay: "60ms" }}>
          <input
            type="search"
            placeholder="▸ Suche nach Titel oder ID …"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="field min-w-[220px] flex-1"
          />
          <select
            value={scheduleFilter}
            onChange={(e) => setScheduleFilter(e.target.value as typeof scheduleFilter)}
            className="field w-auto"
          >
            <option value="">Alle Zeitpläne</option>
            <option value="live">Live</option>
            <option value="nightly">Nightly</option>
          </select>
          <select
            value={geoFilter}
            onChange={(e) => setGeoFilter(e.target.value as typeof geoFilter)}
            className="field w-auto"
          >
            <option value="">Alle</option>
            <option value="geo">Mit Geo</option>
            <option value="nogeo">Ohne Geo</option>
          </select>
        </div>

        {/* Registry */}
        {isLoading ? (
          <p className="py-10 text-center font-mono text-xs text-gotham-500">
            <span className="led mr-2 inline-block animate-led bg-signal-cyan" />
            Lade Quellenregister …
          </p>
        ) : (
          <div className="panel corners animate-rise" style={{ animationDelay: "120ms" }}>
            {filtered.map((d) => {
              const isOpen = expanded === d.id;
              return (
                <div key={d.id} className="border-b border-gotham-750 last:border-0">
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : d.id)}
                    className={clsx(
                      "flex w-full items-center gap-3.5 px-3.5 py-2.5 text-left transition-colors",
                      isOpen ? "bg-gotham-800" : "hover:bg-gotham-800/60"
                    )}
                  >
                    {isOpen ? (
                      <ChevronDown className="h-3.5 w-3.5 shrink-0 text-gotham-500" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-gotham-500" />
                    )}
                    <StatusLed s={d.last_run_status} />

                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium text-gotham-100">{d.title}</p>
                      <div className="mt-0.5 flex items-center gap-2.5 font-mono text-[9px] uppercase tracking-[0.1em]">
                        <span
                          className={clsx(
                            d.schedule === "live" ? "text-signal-green" : "text-gotham-500"
                          )}
                        >
                          [{d.schedule === "live" ? "Live" : "Nightly"}]
                        </span>
                        {d.best_format && <span className="text-gotham-500">{d.best_format}</span>}
                        {d.has_geo && <span className="text-signal-cyan">Geo</span>}
                      </div>
                    </div>

                    <div className="flex shrink-0 items-center gap-2 font-mono text-[10px] text-gotham-500">
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
                        <span className="text-gotham-600">
                          · {d.last_run_rows.toLocaleString()} Zeilen
                        </span>
                      )}
                    </div>
                  </button>

                  {isOpen && <ExpandedPanel datasetId={d.id} />}
                </div>
              );
            })}
            {filtered.length === 0 && (
              <p className="py-8 text-center font-mono text-xs text-gotham-500">
                Keine Quellen für diese Filter.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
