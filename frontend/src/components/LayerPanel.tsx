import { useMapStore, LayerKey } from "../store/mapStore";
import { Layers, ChevronUp, ChevronDown, Check } from "lucide-react";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { useQuery } from "react-query";
import { fetchMetrics, fetchFeatureGroups, FeatureGroup } from "../api/map";
import { datasetColor } from "../map/gothamStyle";

const LAYERS: { key: LayerKey; label: string; desc: string; color: string }[] = [
  { key: "park_ride", label: "Park + Ride", desc: "Auslastung · live 60s", color: "#3dd68c" },
  { key: "bicycle", label: "Radzählstellen", desc: "14-Tage-Aufkommen", color: "#9adcff" },
  { key: "restrictions", label: "Verkehrslagen", desc: "Einschränkungen · live", color: "#ffb02e" },
  { key: "choropleth", label: "Choroplethen", desc: "Statistik je Raumeinheit", color: "#53b9e8" },
  { key: "geo_features", label: "Datenebene", desc: "Alle Geo-Quellen · Vector Tiles", color: "#9d8cff" },
];

function fmtCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

export default function LayerPanel() {
  const [open, setOpen] = useState(true);
  const [datasetSearch, setDatasetSearch] = useState("");
  const {
    activeLayers, toggleLayer,
    choroplethMetric, setChoroplethMetric,
    spatialUnit, setSpatialUnit,
    timelineYear, setTimelineYear,
    selectedDatasetIds, toggleDatasetId,
    selectedFamilyIds, toggleFamilyId,
  } = useMapStore();

  // Metriken je Raumeinheit — nur was dort auch eine Choroplethe ergibt
  const { data: metrics = [] } = useQuery<string[]>(
    ["metrics", spatialUnit],
    () => fetchMetrics(spatialUnit),
    { staleTime: 300_000, enabled: activeLayers.has("choropleth") }
  );

  // Gewählte Metrik zurücksetzen, wenn sie in der neuen Raumeinheit fehlt
  useEffect(() => {
    if (choroplethMetric && metrics.length > 0 && !metrics.includes(choroplethMetric)) {
      setChoroplethMetric("");
    }
  }, [metrics, choroplethMetric, setChoroplethMetric]);

  const { data: featureGroups = [] } = useQuery<FeatureGroup[]>(
    "featureGroups",
    fetchFeatureGroups,
    { staleTime: 600_000, enabled: activeLayers.has("geo_features") }
  );

  const filteredGroups = featureGroups.filter(
    (g) =>
      !datasetSearch ||
      g.title.toLowerCase().includes(datasetSearch.toLowerCase())
  );

  const activeCount = selectedDatasetIds.length + selectedFamilyIds.length;

  return (
    <div className="absolute left-5 top-5 z-10 w-72 animate-rise">
      <div className="panel corners">
        {/* Header */}
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-2.5 border-b border-gotham-700 px-3.5 py-2.5 text-left transition-colors hover:bg-gotham-800"
        >
          <Layers className="h-3.5 w-3.5 text-signal-cyan" />
          <span className="hud-label text-gotham-200">Ebenenkontrolle</span>
          <span className="ml-auto font-mono text-[10px] text-gotham-500">
            {activeLayers.size}/{LAYERS.length}
          </span>
          {open ? (
            <ChevronUp className="h-3.5 w-3.5 text-gotham-500" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-gotham-500" />
          )}
        </button>

        {open && (
          <div className="px-3.5 py-3">
            {/* Layer toggles */}
            <div className="space-y-0.5">
              {LAYERS.map(({ key, label, desc, color }) => {
                const on = activeLayers.has(key);
                return (
                  <button
                    key={key}
                    onClick={() => toggleLayer(key)}
                    className="group flex w-full items-center gap-3 px-1 py-1.5 text-left transition-colors hover:bg-gotham-800/70"
                  >
                    {/* Square checkbox */}
                    <span
                      className={clsx(
                        "flex h-3.5 w-3.5 shrink-0 items-center justify-center border transition-colors",
                        on
                          ? "border-signal-cyan bg-signal-cyan/20"
                          : "border-gotham-500 group-hover:border-gotham-400"
                      )}
                    >
                      {on && <Check className="h-2.5 w-2.5 text-signal-cyan" strokeWidth={3} />}
                    </span>
                    <span
                      className="h-2 w-2 shrink-0"
                      style={{ backgroundColor: color, opacity: on ? 1 : 0.35 }}
                    />
                    <span className="min-w-0 flex-1">
                      <span
                        className={clsx(
                          "block text-xs font-medium transition-colors",
                          on ? "text-gotham-100" : "text-gotham-400 group-hover:text-gotham-300"
                        )}
                      >
                        {label}
                      </span>
                      <span className="block font-mono text-[9px] uppercase tracking-[0.08em] text-gotham-500">
                        {desc}
                      </span>
                    </span>
                    {on && <span className="led animate-led bg-signal-green" />}
                  </button>
                );
              })}
            </div>

            {/* Datenebene: Quellenauswahl (Familien gebündelt mit Jahr-Chips) */}
            {activeLayers.has("geo_features") && (
              <div className="mt-3 space-y-2 border-t border-gotham-700 pt-3">
                <div className="flex items-baseline justify-between">
                  <p className="hud-label">Quellen der Datenebene</p>
                  <span className="font-mono text-[10px] text-gotham-500">
                    {activeCount} aktiv
                  </span>
                </div>
                <input
                  type="search"
                  value={datasetSearch}
                  onChange={(e) => setDatasetSearch(e.target.value)}
                  placeholder="▸ Quelle filtern …"
                  className="field"
                />
                <div className="max-h-52 space-y-0.5 overflow-y-auto pr-1">
                  {featureGroups.length === 0 && (
                    <p className="py-2 text-center font-mono text-[10px] text-gotham-500">
                      Lade Quellen …
                    </p>
                  )}
                  {filteredGroups.map((g) => {
                    const on = g.is_family
                      ? selectedFamilyIds.includes(g.group_id)
                      : selectedDatasetIds.includes(g.group_id);
                    return (
                      <button
                        key={g.group_id}
                        onClick={() =>
                          g.is_family
                            ? toggleFamilyId(g.group_id)
                            : toggleDatasetId(g.group_id)
                        }
                        className="group flex w-full items-center gap-2.5 px-1 py-1 text-left transition-colors hover:bg-gotham-800/70"
                        title={g.title}
                      >
                        <span
                          className={clsx(
                            "flex h-3 w-3 shrink-0 items-center justify-center border transition-colors",
                            on
                              ? "border-signal-cyan bg-signal-cyan/20"
                              : "border-gotham-500 group-hover:border-gotham-400"
                          )}
                        >
                          {on && <Check className="h-2 w-2 text-signal-cyan" strokeWidth={3} />}
                        </span>
                        <span
                          className="h-1.5 w-1.5 shrink-0"
                          style={{
                            backgroundColor: datasetColor(g.group_id),
                            opacity: on ? 1 : 0.35,
                          }}
                        />
                        <span className="min-w-0 flex-1">
                          <span
                            className={clsx(
                              "block truncate text-[11px] transition-colors",
                              on ? "text-gotham-100" : "text-gotham-400 group-hover:text-gotham-300"
                            )}
                          >
                            {g.title}
                          </span>
                          {g.is_family && g.years.length > 0 && (
                            <span className="block truncate font-mono text-[9px] text-gotham-500">
                              {g.years.join(" · ")}
                            </span>
                          )}
                        </span>
                        <span className="shrink-0 font-mono text-[9px] text-gotham-500">
                          {fmtCount(g.feature_count)}
                        </span>
                      </button>
                    );
                  })}
                  {featureGroups.length > 0 && filteredGroups.length === 0 && (
                    <p className="py-2 text-center font-mono text-[10px] text-gotham-500">
                      Keine Treffer.
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Choropleth controls */}
            {activeLayers.has("choropleth") && (
              <div className="mt-3 space-y-2.5 border-t border-gotham-700 pt-3">
                <div>
                  <p className="hud-label mb-1.5">Metrik</p>
                  <select
                    value={choroplethMetric}
                    onChange={(e) => setChoroplethMetric(e.target.value)}
                    className="field"
                  >
                    <option value="">— Metrik wählen —</option>
                    {metrics.map((m: string) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>

                <div className="grid grid-cols-2 gap-2.5">
                  <div>
                    <p className="hud-label mb-1.5">Raumebene</p>
                    <select
                      value={spatialUnit}
                      onChange={(e) => setSpatialUnit(e.target.value)}
                      className="field"
                    >
                      <option value="ortsteil">Ortsteil</option>
                      <option value="stadtbezirk">Stadtbezirk</option>
                      <option value="wahlbezirk">Wahlbezirk</option>
                    </select>
                  </div>
                  <div>
                    <p className="hud-label mb-1.5">Jahr</p>
                    <input
                      type="number"
                      value={timelineYear ?? ""}
                      onChange={(e) => setTimelineYear(e.target.value ? parseInt(e.target.value) : null)}
                      placeholder="neueste"
                      className="field"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
