import { useState } from "react";
import { useQuery } from "react-query";
import { ChevronDown, ChevronRight, BarChart3, Hash, CalendarDays, Type } from "lucide-react";
import { getDatasetHistogram, ProfileColumn } from "../../api/datasets";
import ProfileHistogram from "./ProfileHistogram";
import TopValuesBar from "./TopValuesBar";

function fmtNum(v: number | string | null | undefined): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "string") return v;
  if (!Number.isFinite(v)) return String(v);
  if (Number.isInteger(v)) return v.toLocaleString();
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="whitespace-nowrap">
      <span className="text-gotham-500">{label}&nbsp;</span>
      <span className="text-gotham-200">{value}</span>
    </span>
  );
}

/**
 * Eine Spalte des Datenprofils: Kennzahlen kompakt, Verteilung aufklappbar.
 * Numerische Spalten laden ihr Histogramm lazy beim ersten Aufklappen.
 */
export default function ColumnProfileCard({
  datasetId,
  column,
  color,
}: {
  datasetId: string;
  column: ProfileColumn;
  color: string;
}) {
  const [open, setOpen] = useState(false);
  const expandable =
    (column.kind === "numeric" && !!column.histogram_column) ||
    (column.kind === "categorical" && (column.top?.length ?? 0) > 0);

  const { data: histogram, isLoading } = useQuery(
    ["dataset-histogram", datasetId, column.histogram_column],
    () => getDatasetHistogram(datasetId, column.histogram_column as string),
    {
      enabled: open && column.kind === "numeric" && !!column.histogram_column,
      staleTime: Infinity,
      retry: false,
    }
  );

  const Icon =
    column.kind === "numeric" ? Hash : column.kind === "date" ? CalendarDays : Type;

  return (
    <div className="border-b border-gotham-750 last:border-0">
      <button
        type="button"
        onClick={() => expandable && setOpen((o) => !o)}
        className={
          "flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors " +
          (expandable ? "hover:bg-gotham-800/60" : "cursor-default")
        }
      >
        {expandable ? (
          open ? (
            <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gotham-500" />
          ) : (
            <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gotham-500" />
          )
        ) : (
          <span className="w-3.5 shrink-0" />
        )}
        <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color }} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-gotham-100">{column.name}</p>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-[10px]">
            {column.kind === "numeric" && (
              <>
                <Stat label="Min" value={fmtNum(column.min)} />
                <Stat label="Max" value={fmtNum(column.max)} />
                <Stat label="Mittel" value={fmtNum(column.mean)} />
                <Stat label="Median" value={fmtNum(column.median)} />
                {column.null_share != null && column.null_share > 0 && (
                  <Stat label="Leer" value={`${(column.null_share * 100).toFixed(1)}%`} />
                )}
                {column.year_min != null && (
                  <Stat label="Jahre" value={`${column.year_min}–${column.year_max}`} />
                )}
              </>
            )}
            {column.kind === "categorical" && (
              <>
                <Stat label="Eindeutige Werte" value={fmtNum(column.distinct)} />
                <Stat label="Einträge" value={fmtNum(column.non_null)} />
              </>
            )}
            {column.kind === "date" && (
              <>
                <Stat label="Von" value={fmtNum(column.min)} />
                <Stat label="Bis" value={fmtNum(column.max)} />
              </>
            )}
          </div>
        </div>
        {expandable && <BarChart3 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gotham-500" />}
      </button>

      {open && (
        <div className="bg-gotham-900/70 px-4 pb-3 pt-1">
          {column.kind === "numeric" &&
            (isLoading ? (
              <p className="py-4 text-center font-mono text-[10px] text-gotham-500">
                <span className="led mr-2 inline-block animate-led bg-signal-cyan" />
                Berechne Verteilung …
              </p>
            ) : histogram ? (
              <ProfileHistogram data={histogram} color={color} />
            ) : (
              <p className="py-4 text-center font-mono text-[10px] text-gotham-500">
                Verteilung nicht verfügbar.
              </p>
            ))}
          {column.kind === "categorical" && column.top && (
            <TopValuesBar top={column.top} color={color} />
          )}
        </div>
      )}
    </div>
  );
}
