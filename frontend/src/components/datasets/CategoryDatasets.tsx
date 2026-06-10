import { useState } from "react";
import { useQuery } from "react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ChevronDown, ChevronRight, Layers } from "lucide-react";
import clsx from "clsx";
import { formatDistanceToNow } from "date-fns";
import { de } from "date-fns/locale";
import {
  getCategoryDatasets,
  CategoryDatasetEntry,
} from "../../api/datasets";
import StatusLed from "./StatusLed";

function DatasetRow({ d, indent = false }: { d: CategoryDatasetEntry; indent?: boolean }) {
  return (
    <Link
      to={`/datasets/d/${encodeURIComponent(d.name)}`}
      className={clsx(
        "flex items-center gap-3 border-b border-gotham-750 py-2.5 last:border-0 hover:bg-gotham-800/60",
        indent ? "pl-12 pr-4" : "px-4"
      )}
    >
      <StatusLed s={d.last_run_status} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs text-gotham-100">{d.title}</p>
        <div className="mt-0.5 flex items-center gap-2.5 font-mono text-[9px] uppercase tracking-[0.1em] text-gotham-500">
          <span className={d.schedule === "live" ? "text-signal-green" : ""}>
            [{d.schedule === "live" ? "Live" : "Nightly"}]
          </span>
          {d.best_format && <span>{d.best_format}</span>}
          {d.has_geo && <span className="text-signal-cyan">Geo</span>}
        </div>
      </div>
      <span className="shrink-0 font-mono text-[10px] text-gotham-500">
        {d.last_run_at
          ? formatDistanceToNow(new Date(d.last_run_at), { locale: de, addSuffix: true })
          : "nie"}
      </span>
    </Link>
  );
}

function FamilyGroup({
  title,
  members,
}: {
  title: string | null;
  members: CategoryDatasetEntry[];
}) {
  const [open, setOpen] = useState(false);
  const years = members
    .map((m) => m.family_year)
    .filter((y): y is number => y !== null)
    .sort((a, b) => a - b);

  return (
    <div className="border-b border-gotham-750 last:border-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          "flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors",
          open ? "bg-gotham-800" : "hover:bg-gotham-800/60"
        )}
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-gotham-500" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-gotham-500" />
        )}
        <Layers className="h-3.5 w-3.5 shrink-0 text-signal-violet" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-gotham-100">{title ?? "Zeitreihe"}</p>
          <p className="mt-0.5 font-mono text-[9px] uppercase tracking-[0.1em] text-gotham-500">
            Zeitreihe · {years.length > 0 ? `${years[0]}–${years[years.length - 1]}` : ""} ·{" "}
            {members.length} Jahrgänge
          </p>
        </div>
        <span className="flex shrink-0 flex-wrap justify-end gap-1">
          {years.slice(0, 6).map((y) => (
            <span
              key={y}
              className="border border-gotham-600 px-1.5 py-0.5 font-mono text-[9px] text-gotham-400"
            >
              {y}
            </span>
          ))}
          {years.length > 6 && (
            <span className="font-mono text-[9px] text-gotham-500">+{years.length - 6}</span>
          )}
        </span>
      </button>
      {open && (
        <div className="bg-gotham-900/70">
          {members.map((m) => (
            <DatasetRow key={m.id} d={m} indent />
          ))}
        </div>
      )}
    </div>
  );
}

export default function CategoryDatasets() {
  const { categoryId = "" } = useParams<{ categoryId: string }>();

  const { data, isLoading } = useQuery(
    ["categoryDatasets", categoryId],
    () => getCategoryDatasets(categoryId),
    { enabled: !!categoryId, staleTime: 300_000 }
  );

  const total =
    (data?.datasets.length ?? 0) +
    (data?.families.reduce((s, f) => s + f.members.length, 0) ?? 0);

  return (
    <div className="blueprint-bg h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-5 p-6 lg:p-8">
        <header className="animate-rise">
          <Link
            to="/datasets"
            className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.14em] text-signal-cyan hover:text-signal-bright"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Themenkatalog
          </Link>
          <p className="hud-label mt-3 text-signal-cyan">Modul 03 // Datenbestand</p>
          <h1 className="mt-1 font-display text-2xl font-bold uppercase tracking-[0.12em] text-gotham-100">
            {data?.category.title ?? "…"}
          </h1>
          {data?.category.description && (
            <p className="mt-1 max-w-2xl font-mono text-[11px] leading-relaxed text-gotham-400">
              {data.category.description}
            </p>
          )}
        </header>

        {isLoading ? (
          <p className="py-10 text-center font-mono text-xs text-gotham-500">
            <span className="led mr-2 inline-block animate-led bg-signal-cyan" />
            Lade Datensätze …
          </p>
        ) : (
          <div className="panel corners animate-rise" style={{ animationDelay: "80ms" }}>
            <div className="flex items-center justify-between border-b border-gotham-700 px-4 py-2.5">
              <p className="hud-label text-gotham-200">Datensätze</p>
              <p className="font-mono text-[10px] text-gotham-500">{total} Quellen</p>
            </div>
            {data?.families.map((f) => (
              <FamilyGroup key={f.family_id} title={f.title} members={f.members} />
            ))}
            {data?.datasets.map((d) => (
              <DatasetRow key={d.id} d={d} />
            ))}
            {total === 0 && (
              <p className="p-6 text-center font-mono text-xs text-gotham-500">
                Keine Datensätze in diesem Thema.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
