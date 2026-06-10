import { useEffect, useMemo, useState } from "react";
import { useQuery } from "react-query";
import clsx from "clsx";
import {
  Layers, ChevronUp, ChevronDown, ChevronRight, Check, X,
  MapPin, Map as MapIcon, Activity, BarChart3,
} from "lucide-react";
import { fetchCatalog, CatalogEntry, CatalogKind } from "../api/catalog";
import { listCategories, Category } from "../api/datasets";
import { fetchMetrics } from "../api/map";
import { useMapStore } from "../store/mapStore";
import { datasetColor } from "../map/gothamStyle";
import { PRESETS, applyEntry, isEntryActive } from "../lagebild/catalog-actions";

const BADGE_CLASS: Record<string, string> = {
  Live: "border-signal-green/40 text-signal-green",
  Geo: "border-signal-cyan/40 text-signal-cyan",
  Ortsteil: "border-signal-violet/40 text-signal-violet",
  Stadt: "border-signal-bright/40 text-signal-bright",
  Zeitreihe: "border-signal-amber/40 text-signal-amber",
};

const KIND_ICON: Record<CatalogKind, typeof MapPin> = {
  geo: MapPin,
  choropleth: MapIcon,
  timeseries: Activity,
  distribution: BarChart3,
};

function fmtCount(n: number | null): string {
  if (!n) return "";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

export default function CatalogPanel() {
  const [open, setOpen] = useState(true);
  const [search, setSearch] = useState("");
  const [openThemes, setOpenThemes] = useState<Set<string>>(new Set());
  const store = useMapStore();

  const { data: catalog = [] } = useQuery<CatalogEntry[]>("catalog", fetchCatalog, {
    staleTime: 600_000,
  });
  const { data: categories = [] } = useQuery<Category[]>("categories", listCategories, {
    staleTime: 600_000,
  });

  const themeTitle = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of categories) m.set(c.category_id, c.title);
    return (id: string) => m.get(id) ?? "Sonstiges";
  }, [categories]);

  const themeOrder = useMemo(() => {
    const m = new Map<string, number>();
    categories.forEach((c) => m.set(c.category_id, c.position));
    return m;
  }, [categories]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? catalog.filter((e) => e.title.toLowerCase().includes(q)) : catalog;
  }, [catalog, search]);

  const themes = useMemo(() => {
    const groups = new Map<string, CatalogEntry[]>();
    for (const e of filtered) {
      const list = groups.get(e.theme) ?? [];
      list.push(e);
      groups.set(e.theme, list);
    }
    return [...groups.entries()]
      .map(([id, entries]) => ({
        id,
        title: themeTitle(id),
        entries: entries.sort((a, b) => a.title.localeCompare(b.title)),
      }))
      .sort(
        (a, b) =>
          (themeOrder.get(a.id) ?? 99) - (themeOrder.get(b.id) ?? 99) ||
          a.title.localeCompare(b.title)
      );
  }, [filtered, themeTitle, themeOrder]);

  // Auto-open themes that contain a match while searching.
  const effectiveOpen = search ? new Set(themes.map((t) => t.id)) : openThemes;

  const activeEntries = useMemo(
    () => catalog.filter((e) => isEntryActive(e, store)),
    [catalog, store]
  );

  const applyPreset = (presetId: string) => {
    const preset = PRESETS.find((p) => p.id === presetId);
    if (!preset) return;
    catalog.filter(preset.match).forEach((e) => applyEntry(e, store, true));
    preset.layers?.forEach((l) => store.setLayer(l, true));
    setOpenThemes(new Set(catalog.filter(preset.match).map((e) => e.theme)));
  };

  const toggleTheme = (id: string) =>
    setOpenThemes((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="absolute left-5 top-5 z-10 w-80 animate-rise">
      <div className="panel corners">
        {/* Header */}
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-2.5 border-b border-gotham-700 px-3.5 py-2.5 text-left transition-colors hover:bg-gotham-800"
        >
          <Layers className="h-3.5 w-3.5 text-signal-cyan" />
          <span className="hud-label text-gotham-200">Datenkatalog</span>
          <span className="ml-auto font-mono text-[10px] text-gotham-500">
            {activeEntries.length} aktiv
          </span>
          {open ? (
            <ChevronUp className="h-3.5 w-3.5 text-gotham-500" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-gotham-500" />
          )}
        </button>

        {open && (
          <div className="px-3 py-3">
            {/* Presets */}
            <div className="mb-2.5 flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => applyPreset(p.id)}
                  className="border border-gotham-600 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-gotham-300 transition-colors hover:border-signal-cyan hover:text-signal-cyan"
                >
                  {p.label}
                </button>
              ))}
            </div>

            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="▸ Datensatz suchen …"
              className="field mb-2"
            />

            {/* Theme accordion */}
            <div className="max-h-[42vh] space-y-0.5 overflow-y-auto pr-1">
              {catalog.length === 0 && (
                <p className="py-3 text-center font-mono text-[10px] text-gotham-500">
                  Lade Katalog …
                </p>
              )}
              {themes.map((theme) => {
                const isOpen = effectiveOpen.has(theme.id);
                return (
                  <div key={theme.id}>
                    <button
                      onClick={() => toggleTheme(theme.id)}
                      className="flex w-full items-center gap-2 px-1 py-1.5 text-left transition-colors hover:bg-gotham-800/70"
                    >
                      <ChevronRight
                        className={clsx(
                          "h-3 w-3 shrink-0 text-gotham-500 transition-transform",
                          isOpen && "rotate-90"
                        )}
                      />
                      <span className="flex-1 truncate text-[11px] font-medium uppercase tracking-[0.06em] text-gotham-200">
                        {theme.title}
                      </span>
                      <span className="font-mono text-[9px] text-gotham-500">
                        {theme.entries.length}
                      </span>
                    </button>
                    {isOpen && (
                      <div className="space-y-0.5 pb-1 pl-2">
                        {theme.entries.map((e) => (
                          <EntryRow key={e.group_id} entry={e} />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Active stack */}
            {activeEntries.length > 0 && (
              <div className="mt-3 space-y-2 border-t border-gotham-700 pt-2.5">
                <p className="hud-label">Aktive Ebenen</p>
                <div className="space-y-0.5">
                  {activeEntries.map((e) => (
                    <ActiveRow key={e.group_id} entry={e} />
                  ))}
                </div>
                {store.choroplethDatasetId && <ChoroplethControl />}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Badges({ badges }: { badges: string[] }) {
  return (
    <span className="flex shrink-0 gap-1">
      {badges.map((b) => (
        <span
          key={b}
          className={clsx(
            "border px-1 font-mono text-[8px] uppercase leading-tight tracking-wide",
            BADGE_CLASS[b] ?? "border-gotham-600 text-gotham-400"
          )}
        >
          {b}
        </span>
      ))}
    </span>
  );
}

function EntryRow({ entry }: { entry: CatalogEntry }) {
  const store = useMapStore();
  const on = isEntryActive(entry, store);
  const Icon = KIND_ICON[entry.kind];
  return (
    <button
      onClick={() => applyEntry(entry, store)}
      title={entry.title}
      className="group flex w-full items-center gap-2 px-1 py-1 text-left transition-colors hover:bg-gotham-800/70"
    >
      <span
        className={clsx(
          "flex h-3 w-3 shrink-0 items-center justify-center border transition-colors",
          on ? "border-signal-cyan bg-signal-cyan/20" : "border-gotham-500 group-hover:border-gotham-400"
        )}
      >
        {on && <Check className="h-2 w-2 text-signal-cyan" strokeWidth={3} />}
      </span>
      <Icon className="h-3 w-3 shrink-0 text-gotham-500" />
      <span
        className={clsx(
          "min-w-0 flex-1 truncate text-[11px] transition-colors",
          on ? "text-gotham-100" : "text-gotham-400 group-hover:text-gotham-300"
        )}
      >
        {entry.title}
      </span>
      <Badges badges={entry.badges} />
      {entry.feature_count != null && (
        <span className="shrink-0 font-mono text-[9px] text-gotham-500">
          {fmtCount(entry.feature_count)}
        </span>
      )}
    </button>
  );
}

function ActiveRow({ entry }: { entry: CatalogEntry }) {
  const store = useMapStore();
  return (
    <div className="flex items-center gap-2 px-1 py-1">
      <span
        className="h-1.5 w-1.5 shrink-0"
        style={{ backgroundColor: datasetColor(entry.dataset_ids[0]) }}
      />
      <span className="min-w-0 flex-1 truncate text-[11px] text-gotham-100">{entry.title}</span>
      <button
        onClick={() => applyEntry(entry, store, false)}
        className="shrink-0 text-gotham-500 transition-colors hover:text-signal-red"
        title="Entfernen"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

/** Metric + spatial unit + year picker for the active choropleth dataset. */
function ChoroplethControl() {
  const {
    choroplethDatasetId, choroplethMetric, setChoropleth,
    spatialUnit, setSpatialUnit, timelineYear, setTimelineYear,
  } = useMapStore();

  const { data: metrics = [] } = useQuery<string[]>(
    ["metrics", spatialUnit, choroplethDatasetId],
    () => fetchMetrics(spatialUnit, choroplethDatasetId ?? undefined),
    { enabled: !!choroplethDatasetId, staleTime: 300_000 }
  );

  // Default to the first available metric once they load (or when the current
  // one isn't valid for this dataset/spatial unit).
  useEffect(() => {
    if (metrics.length && !metrics.includes(choroplethMetric)) {
      setChoropleth(choroplethDatasetId, metrics[0]);
    }
  }, [metrics, choroplethMetric, choroplethDatasetId, setChoropleth]);

  const metric = metrics.includes(choroplethMetric) ? choroplethMetric : "";

  return (
    <div className="space-y-2 border-t border-gotham-800 pt-2">
      <p className="hud-label">Choroplethe</p>
      <select
        value={metric}
        onChange={(e) => setChoropleth(choroplethDatasetId, e.target.value)}
        className="field"
      >
        {metrics.length === 0 && <option value="">— keine kartierbare Metrik —</option>}
        {metrics.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
      <div className="grid grid-cols-2 gap-2">
        <select
          value={spatialUnit}
          onChange={(e) => setSpatialUnit(e.target.value)}
          className="field"
        >
          <option value="ortsteil">Ortsteil</option>
          <option value="stadtbezirk">Stadtbezirk</option>
          <option value="wahlbezirk">Wahlbezirk</option>
        </select>
        <input
          type="number"
          value={timelineYear ?? ""}
          onChange={(e) => setTimelineYear(e.target.value ? parseInt(e.target.value) : null)}
          placeholder="neueste"
          className="field"
        />
      </div>
    </div>
  );
}
