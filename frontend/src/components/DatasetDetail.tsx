import { useState } from "react";
import { useQuery } from "react-query";
import { Link, useParams } from "react-router-dom";
import {
  getDatasetBySlug,
  getDatasetHistory,
  getDatasetProfile,
  getDatasetRows,
} from "../api/datasets";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import { de } from "date-fns/locale";
import ColumnProfileCard from "./datasets/ColumnProfileCard";
import ElectionResultsPanel from "./datasets/ElectionResultsPanel";
import { datasetColor } from "../map/gothamStyle";

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
  const { slug = "" } = useParams<{ slug: string }>();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  const { data: detail } = useQuery(
    ["dataset-by-slug", slug],
    () => getDatasetBySlug(slug),
    { enabled: !!slug }
  );
  // Sub-Ressourcen laufen intern weiter über die Dataset-ID
  const datasetId = detail?.dataset.id ?? "";
  const { data: profile, isLoading: profileLoading } = useQuery(
    ["dataset-profile", datasetId],
    () => getDatasetProfile(datasetId),
    { enabled: !!datasetId, staleTime: 300_000 }
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
      <div className="blueprint-bg h-full p-8">
        <Link
          to="/datasets"
          className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-signal-cyan hover:text-signal-bright"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Zum Themenkatalog
        </Link>
        <p className="mt-6 font-mono text-xs text-gotham-500">
          <span className="led mr-2 inline-block animate-led bg-signal-cyan" />
          Lade Quelldaten …
        </p>
      </div>
    );
  }

  const ds = detail.dataset;
  const totalPages = rows ? Math.ceil(rows.total / PAGE_SIZE) : 0;
  // Semantische Wahl-Domäne: election_id aus den Zeilen ableiten
  const electionId =
    detail.target_table === "core.election_results"
      ? (rows?.items?.[0]?.election_id as string | undefined)
      : undefined;

  return (
    <div className="blueprint-bg h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-5 p-6 lg:p-8">
        {/* Header */}
        <header className="animate-rise">
          <Link
            to={
              detail.categories?.length
                ? `/datasets/c/${encodeURIComponent(detail.categories[0].category_id)}`
                : "/datasets"
            }
            className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-signal-cyan hover:text-signal-bright"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Zur Kategorie
          </Link>
          <p className="hud-label mt-3 text-signal-cyan">Modul 03 // Quellakte</p>
          <h1 className="mt-1 font-display text-2xl font-bold uppercase tracking-[0.1em] text-gotham-100">
            {ds.title}
          </h1>
          {(detail.categories?.length || ds.family_id) && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {detail.categories?.map((c) => (
                <Link
                  key={c.category_id}
                  to={`/datasets/c/${encodeURIComponent(c.category_id)}`}
                  className="border border-gotham-600 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] text-gotham-300 hover:border-signal-cyan hover:text-signal-cyan"
                >
                  {c.title}
                </Link>
              ))}
              {ds.family_id && (
                <span className="border border-signal-violet/50 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] text-signal-violet">
                  Zeitreihe{ds.family_year ? ` · ${ds.family_year}` : ""}
                </span>
              )}
            </div>
          )}
        </header>

        {/* Metadata */}
        <section className="panel corners p-4 animate-rise" style={{ animationDelay: "60ms" }}>
          <p className="hud-label mb-3 border-b border-gotham-700 pb-2.5 text-gotham-200">
            Stammdaten
          </p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 font-mono text-[11px] text-gotham-300 md:grid-cols-3">
            <div><span className="text-gotham-500">Zeitplan&nbsp;&nbsp;</span>{ds.schedule}</div>
            <div><span className="text-gotham-500">Format&nbsp;&nbsp;</span>{ds.best_format ?? "–"}</div>
            <div>
              <span className="text-gotham-500">Geo&nbsp;&nbsp;</span>
              {ds.has_geo ? <span className="text-signal-cyan">ja</span> : "nein"}
            </div>
            <div><span className="text-gotham-500">Tabelle&nbsp;&nbsp;</span><code>{detail.target_table ?? "–"}</code></div>
            <div>
              <span className="text-gotham-500">Zeilen&nbsp;&nbsp;</span>
              <span className="font-semibold text-signal-bright">{detail.row_count.toLocaleString()}</span>
            </div>
            <div className="md:col-span-3">
              <span className="text-gotham-500">Letzter ETL&nbsp;&nbsp;</span>
              {ds.last_ingested
                ? `${formatDistanceToNow(new Date(ds.last_ingested), { locale: de, addSuffix: true })} (${format(new Date(ds.last_ingested), "yyyy-MM-dd HH:mm")})`
                : "nie"}
            </div>
            {ds.best_url && (
              <div className="truncate md:col-span-3">
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
        </section>

        {/* Wahlergebnis (semantisch vereinheitlichte Domäne) */}
        {electionId && (
          <section className="panel corners animate-rise" style={{ animationDelay: "100ms" }}>
            <div className="border-b border-gotham-700 px-4 py-3">
              <p className="hud-label text-gotham-200">Wahlergebnis · Stadt Leipzig</p>
            </div>
            <ElectionResultsPanel electionId={electionId} />
          </section>
        )}

        {/* Datenprofil: Spalten-Statistiken + Verteilungen */}
        <section className="panel animate-rise" style={{ animationDelay: "120ms" }}>
          <div className="flex items-center justify-between border-b border-gotham-700 px-4 py-3">
            <p className="hud-label text-gotham-200">Datenprofil</p>
            {profile && (
              <p className="font-mono text-[10px] text-gotham-500">
                {profile.columns.length} Merkmale · {profile.row_count.toLocaleString()} Zeilen
              </p>
            )}
          </div>
          {profileLoading ? (
            <p className="p-6 text-center font-mono text-xs text-gotham-500">
              <span className="led mr-2 inline-block animate-led bg-signal-cyan" />
              Profiliere Daten …
            </p>
          ) : !profile || profile.columns.length === 0 ? (
            <p className="p-6 text-center font-mono text-xs text-gotham-500">
              Kein Profil verfügbar.
            </p>
          ) : (
            profile.columns.map((col) => (
              <ColumnProfileCard
                key={col.name}
                datasetId={datasetId}
                column={col}
                color={datasetColor(datasetId)}
              />
            ))
          )}
        </section>

        {/* Rows */}
        <section className="panel animate-rise" style={{ animationDelay: "180ms" }}>
          <div className="flex items-center justify-between border-b border-gotham-700 px-4 py-3">
            <p className="hud-label text-gotham-200">Einträge</p>
            {rows && (
              <p className="font-mono text-[10px] text-gotham-500">
                {rows.total.toLocaleString()} insgesamt
              </p>
            )}
          </div>
          <div className="border-b border-gotham-700 p-3">
            <input
              type="search"
              placeholder="▸ In Einträgen suchen …"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(0);
              }}
              className="field"
            />
          </div>

          {rowsLoading ? (
            <p className="p-6 text-center font-mono text-xs text-gotham-500">Lade Einträge …</p>
          ) : !rows || rows.items.length === 0 ? (
            <p className="p-6 text-center font-mono text-xs text-gotham-500">Keine Einträge gefunden.</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full font-mono text-[11px]">
                  <thead className="bg-gotham-900/60">
                    <tr className="border-b border-gotham-700 text-gotham-500">
                      {rows.columns.map((c) => (
                        <th key={c} className="px-3 py-2 text-left font-medium uppercase tracking-[0.08em]">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="text-gotham-200">
                    {rows.items.map((row, i) => (
                      <tr key={i} className="border-b border-gotham-750 last:border-0 hover:bg-gotham-800/50">
                        {rows.columns.map((c) => (
                          <td key={c} className="max-w-[260px] truncate px-3 py-1.5">
                            {fmt(row[c])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between border-t border-gotham-700 px-3 py-2 font-mono text-[10px] text-gotham-400">
                <span>
                  Seite {page + 1} / {Math.max(1, totalPages)}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="btn-ghost"
                  >
                    ◂ Zurück
                  </button>
                  <button
                    type="button"
                    onClick={() => setPage((p) => (p + 1 < totalPages ? p + 1 : p))}
                    disabled={page + 1 >= totalPages}
                    className="btn-ghost"
                  >
                    Weiter ▸
                  </button>
                </div>
              </div>
            </>
          )}
        </section>

        {/* History */}
        <section className="panel p-4 animate-rise" style={{ animationDelay: "240ms" }}>
          <p className="hud-label mb-3 border-b border-gotham-700 pb-2.5 text-gotham-200">
            ETL-Historie
          </p>
          {!history || history.history.length === 0 ? (
            <p className="font-mono text-[11px] text-gotham-500">Noch keine Änderungen aufgezeichnet.</p>
          ) : (
            <ul className="space-y-0 font-mono text-[11px]">
              {history.history.map((h) => (
                <li
                  key={h.id}
                  className="flex items-start gap-3 border-b border-gotham-750 py-2 first:pt-0 last:border-0 last:pb-0"
                >
                  <span
                    className={
                      h.status === "failed"
                        ? "led mt-1.5 bg-signal-red"
                        : "led mt-1.5 bg-signal-green"
                    }
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-gotham-300">
                      {format(new Date(h.created_at), "yyyy-MM-dd HH:mm")}
                      {"  —  "}
                      <span className="text-signal-green">+{h.rows_added}</span>
                      {" / "}
                      <span className="text-signal-amber">~{h.rows_updated}</span>
                      {" → "}
                      <span className="text-gotham-100">
                        {h.rows_total_after?.toLocaleString() ?? "?"} Zeilen total
                      </span>
                    </p>
                    <p className="text-[10px] text-gotham-500">
                      {h.target_table}
                      {h.duration_ms ? ` · ${(h.duration_ms / 1000).toFixed(1)}s` : ""}
                      {h.status ? ` · ${h.status}` : ""}
                    </p>
                    {h.error_message && (
                      <p className="truncate text-[10px] text-signal-red">{h.error_message}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
