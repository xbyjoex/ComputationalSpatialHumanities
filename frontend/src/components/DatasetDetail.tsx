import { useState } from "react";
import { useQuery } from "react-query";
import { Link, useParams } from "react-router-dom";
import {
  getDataset,
  getDatasetHistory,
  getDatasetRows,
  getDatasetStats,
} from "../api/datasets";
import {
  ArrowLeft,
  Database,
  Clock,
  TrendingUp,
  History,
  ExternalLink,
} from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import { de } from "date-fns/locale";

const PAGE_SIZE = 50;

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return String(v);
    return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
  }
  if (typeof v === "object") return JSON.stringify(v).slice(0, 80);
  return String(v);
}

export default function DatasetDetail() {
  const { datasetId = "" } = useParams<{ datasetId: string }>();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  const { data: detail } = useQuery(["dataset", datasetId], () => getDataset(datasetId), {
    enabled: !!datasetId,
  });
  const { data: stats } = useQuery(
    ["dataset-stats", datasetId],
    () => getDatasetStats(datasetId),
    { enabled: !!datasetId }
  );
  const { data: rows, isLoading: rowsLoading } = useQuery(
    ["dataset-rows", datasetId, search, page],
    () =>
      getDatasetRows(datasetId, {
        search: search || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }),
    { enabled: !!datasetId, keepPreviousData: true }
  );
  const { data: history } = useQuery(
    ["dataset-history", datasetId],
    () => getDatasetHistory(datasetId, 50),
    { enabled: !!datasetId }
  );

  if (!detail) {
    return (
      <div className="p-6">
        <Link to="/datasets" className="text-brand-400 hover:underline inline-flex items-center gap-1">
          <ArrowLeft className="w-4 h-4" /> Zurück zur Liste
        </Link>
        <p className="text-slate-500 mt-4">Lade …</p>
      </div>
    );
  }

  const ds = detail.dataset;
  const totalPages = rows ? Math.ceil(rows.total / PAGE_SIZE) : 0;

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div>
        <Link
          to="/datasets"
          className="text-brand-400 hover:underline inline-flex items-center gap-1 text-sm"
        >
          <ArrowLeft className="w-4 h-4" /> Zurück zur Liste
        </Link>
        <div className="flex items-center gap-3 mt-2">
          <Database className="w-5 h-5 text-brand-400" />
          <h1 className="text-xl font-bold text-white">{ds.title}</h1>
        </div>
      </div>

      {/* Metadata card */}
      <section className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-2 text-sm">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-2 text-slate-300">
          <div><span className="text-slate-500">ID:</span> <code>{ds.id}</code></div>
          <div><span className="text-slate-500">Zeitplan:</span> {ds.schedule}</div>
          <div><span className="text-slate-500">Format:</span> {ds.best_format ?? "–"}</div>
          <div><span className="text-slate-500">Geo:</span> {ds.has_geo ? "ja" : "nein"}</div>
          <div><span className="text-slate-500">Tabelle:</span> <code>{detail.target_table ?? "–"}</code></div>
          <div>
            <span className="text-slate-500">Zeilen:</span>{" "}
            <span className="text-white font-semibold">{detail.row_count.toLocaleString()}</span>
          </div>
          <div className="md:col-span-3">
            <span className="text-slate-500">Letzter ETL:</span>{" "}
            {ds.last_ingested
              ? `${formatDistanceToNow(new Date(ds.last_ingested), { locale: de, addSuffix: true })} (${format(new Date(ds.last_ingested), "yyyy-MM-dd HH:mm")})`
              : "nie"}
          </div>
          {ds.best_url && (
            <div className="md:col-span-3 truncate">
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
      </section>

      {/* Stats */}
      <section>
        <h2 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-brand-400" /> Statistiken
        </h2>
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
          <StatsBlock stats={stats} />
        </div>
      </section>

      {/* Rows */}
      <section>
        <h2 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
          <Database className="w-4 h-4 text-brand-400" /> Einträge
          {rows && (
            <span className="text-slate-500 font-normal text-xs">
              {rows.total.toLocaleString()} insgesamt
            </span>
          )}
        </h2>
        <div className="bg-slate-800 border border-slate-700 rounded-xl">
          <div className="p-3 border-b border-slate-700">
            <input
              type="search"
              placeholder="In Einträgen suchen …"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>

          {rowsLoading ? (
            <p className="text-slate-500 text-sm p-6 text-center">Lade Einträge …</p>
          ) : !rows || rows.items.length === 0 ? (
            <p className="text-slate-500 text-sm p-6 text-center">Keine Einträge gefunden.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-900/50">
                    <tr className="text-slate-400 border-b border-slate-700">
                      {rows.columns.map((c) => (
                        <th key={c} className="text-left font-medium px-3 py-2">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="text-slate-200">
                    {rows.items.map((row, i) => (
                      <tr key={i} className="border-b border-slate-800 last:border-0 hover:bg-slate-900/30">
                        {rows.columns.map((c) => (
                          <td key={c} className="px-3 py-1.5 truncate max-w-[260px]">
                            {fmt(row[c])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between px-3 py-2 border-t border-slate-700 text-xs text-slate-400">
                <span>
                  Seite {page + 1} / {Math.max(1, totalPages)}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-40"
                  >
                    Zurück
                  </button>
                  <button
                    type="button"
                    onClick={() => setPage((p) => (p + 1 < totalPages ? p + 1 : p))}
                    disabled={page + 1 >= totalPages}
                    className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-40"
                  >
                    Weiter
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </section>

      {/* History */}
      <section>
        <h2 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
          <History className="w-4 h-4 text-brand-400" /> ETL-Historie
        </h2>
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
          {!history || history.history.length === 0 ? (
            <p className="text-slate-500 text-xs">Noch keine Änderungen aufgezeichnet.</p>
          ) : (
            <ul className="space-y-2 text-xs">
              {history.history.map((h) => (
                <li
                  key={h.id}
                  className="flex items-start gap-3 pb-2 border-b border-slate-700 last:border-0 last:pb-0"
                >
                  <Clock className="w-3.5 h-3.5 text-slate-500 mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-slate-300">
                      {format(new Date(h.created_at), "yyyy-MM-dd HH:mm")}
                      {" — "}
                      <span className="text-green-400">+{h.rows_added}</span>
                      {" / "}
                      <span className="text-yellow-400">~{h.rows_updated}</span>
                      {" → "}
                      <span className="text-slate-200">
                        {h.rows_total_after?.toLocaleString() ?? "?"} Zeilen total
                      </span>
                    </p>
                    <p className="text-slate-500 text-[11px]">
                      {h.target_table}
                      {h.duration_ms ? ` · ${(h.duration_ms / 1000).toFixed(1)}s` : ""}
                      {h.status ? ` · ${h.status}` : ""}
                    </p>
                    {h.error_message && (
                      <p className="text-red-400 text-[11px] truncate">{h.error_message}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}

function StatsBlock({
  stats,
}: {
  stats: Awaited<ReturnType<typeof getDatasetStats>> | undefined;
}) {
  if (!stats) return <p className="text-slate-500 text-xs">Lade …</p>;
  if (!stats.target_table) {
    return <p className="text-slate-500 text-xs">Keine Daten geladen.</p>;
  }

  const buckets =
    stats.per_metric ?? stats.per_type ?? stats.per_site ?? stats.per_counter ?? [];
  if (buckets.length === 0) {
    return (
      <pre className="text-xs text-slate-400 whitespace-pre-wrap">
        {JSON.stringify(stats.summary ?? {}, null, 2)}
      </pre>
    );
  }
  const keys = Object.keys(buckets[0]);
  return (
    <>
      {stats.summary && (
        <div className="text-xs text-slate-400 mb-3 flex flex-wrap gap-x-4 gap-y-1">
          {Object.entries(stats.summary).map(([k, v]) => (
            <span key={k}>
              <span className="text-slate-500">{k}:</span>{" "}
              <span className="text-slate-200">{fmt(v)}</span>
            </span>
          ))}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500 border-b border-slate-700">
              {keys.map((k) => (
                <th key={k} className="text-left font-medium py-1.5 pr-3">
                  {k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-slate-200">
            {buckets.map((row, i) => (
              <tr key={i} className="border-b border-slate-800 last:border-0">
                {keys.map((k) => (
                  <td key={k} className="py-1 pr-3 truncate max-w-[220px]">
                    {fmt(row[k])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
