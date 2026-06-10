import { useState } from "react";
import { useQuery } from "react-query";
import { Link } from "react-router-dom";
import { FolderOpen, ChevronRight, Database } from "lucide-react";
import { listCategories, listDatasets, Category } from "../../api/datasets";

/**
 * Themenkatalog: Einstieg in den Datenbestand über die 13 DCAT-Kategorien
 * von opendata.leipzig.de (+ Sonstiges). Die Suche schaltet auf eine flache
 * Trefferliste über alle Kategorien hinweg.
 */
export default function CategoryGrid() {
  const [search, setSearch] = useState("");

  const { data: categories = [], isLoading } = useQuery<Category[]>(
    "datasetCategories",
    listCategories,
    { staleTime: 300_000 }
  );

  const { data: searchResults } = useQuery(
    ["datasetSearch", search],
    () => listDatasets({ search, limit: 50 }),
    { enabled: search.length >= 2, keepPreviousData: true }
  );

  const totalDatasets = categories.reduce((s, c) => s + c.dataset_count, 0);

  return (
    <div className="blueprint-bg h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-5 p-6 lg:p-8">
        <header className="flex items-end justify-between animate-rise">
          <div>
            <p className="hud-label text-signal-cyan">Modul 03 // Datenbestand</p>
            <h1 className="mt-1 font-display text-2xl font-bold uppercase tracking-[0.12em] text-gotham-100">
              Themenkatalog
            </h1>
            <p className="mt-1 font-mono text-[11px] text-gotham-400">
              398 Quellen der Stadt Leipzig, thematisch geordnet
            </p>
          </div>
          <Link
            to="/datasets/register"
            className="inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-[0.12em] text-signal-cyan hover:text-signal-bright"
          >
            Technisches Quellenregister <ChevronRight className="h-3 w-3" />
          </Link>
        </header>

        <div className="animate-rise" style={{ animationDelay: "60ms" }}>
          <input
            type="search"
            placeholder="▸ Datensatz über alle Themen suchen …"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="field"
          />
        </div>

        {/* Suchmodus: flache Trefferliste */}
        {search.length >= 2 ? (
          <div className="panel corners animate-rise">
            <div className="flex items-center justify-between border-b border-gotham-700 px-4 py-2.5">
              <p className="hud-label text-gotham-200">Suchtreffer</p>
              <p className="font-mono text-[10px] text-gotham-500">
                {searchResults?.total ?? "…"} Treffer
              </p>
            </div>
            {(searchResults?.items ?? []).map((d) => (
              <Link
                key={d.id}
                to={`/datasets/d/${encodeURIComponent(d.name ?? d.id)}`}
                className="flex items-center gap-3 border-b border-gotham-750 px-4 py-2.5 last:border-0 hover:bg-gotham-800/60"
              >
                <Database className="h-3.5 w-3.5 shrink-0 text-gotham-500" />
                <span className="min-w-0 flex-1 truncate text-xs text-gotham-100">{d.title}</span>
                <span className="shrink-0 font-mono text-[9px] uppercase text-gotham-500">
                  {d.best_format ?? ""}
                  {d.has_geo && <span className="ml-2 text-signal-cyan">Geo</span>}
                </span>
              </Link>
            ))}
            {searchResults && searchResults.items.length === 0 && (
              <p className="p-6 text-center font-mono text-xs text-gotham-500">
                Keine Quellen gefunden.
              </p>
            )}
          </div>
        ) : isLoading ? (
          <p className="py-10 text-center font-mono text-xs text-gotham-500">
            <span className="led mr-2 inline-block animate-led bg-signal-cyan" />
            Lade Themenkatalog …
          </p>
        ) : (
          <>
            <div
              className="grid grid-cols-1 gap-3 animate-rise sm:grid-cols-2 lg:grid-cols-3"
              style={{ animationDelay: "120ms" }}
            >
              {categories.map((c) => (
                <Link
                  key={c.category_id}
                  to={`/datasets/c/${encodeURIComponent(c.category_id)}`}
                  className="panel corners group flex flex-col justify-between p-4 transition-colors hover:bg-gotham-800/70"
                >
                  <div className="flex items-start gap-3">
                    <FolderOpen className="mt-0.5 h-4 w-4 shrink-0 text-signal-cyan" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gotham-100 group-hover:text-white">
                        {c.title}
                      </p>
                      {c.description && (
                        <p className="mt-1 line-clamp-2 font-mono text-[10px] leading-relaxed text-gotham-500">
                          {c.description}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-4 font-mono text-[10px] text-gotham-400">
                    <span>
                      <span className="font-semibold text-signal-bright">{c.dataset_count}</span>{" "}
                      Datensätze
                    </span>
                    {c.geo_count > 0 && (
                      <span className="text-signal-cyan">{c.geo_count} mit Geo</span>
                    )}
                    <ChevronRight className="ml-auto h-3 w-3 text-gotham-500 group-hover:text-signal-cyan" />
                  </div>
                </Link>
              ))}
            </div>
            <p className="font-mono text-[10px] text-gotham-500">
              {totalDatasets.toLocaleString()} Zuordnungen — Mehrfachzuordnung zu Themen möglich.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
