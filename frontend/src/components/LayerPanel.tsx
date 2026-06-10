import { useMapStore, LayerKey } from "../store/mapStore";
import { Layers, ChevronUp, ChevronDown, Check } from "lucide-react";
import clsx from "clsx";
import { useState } from "react";
import { useQuery } from "react-query";
import { fetchMetrics } from "../api/map";

const LAYERS: { key: LayerKey; label: string; desc: string; color: string }[] = [
  { key: "park_ride", label: "Park + Ride", desc: "Auslastung · live 60s", color: "#3dd68c" },
  { key: "bicycle", label: "Radzählstellen", desc: "14-Tage-Aufkommen", color: "#9adcff" },
  { key: "restrictions", label: "Verkehrslagen", desc: "Einschränkungen · live", color: "#ffb02e" },
  { key: "choropleth", label: "Choroplethen", desc: "Statistik je Raumeinheit", color: "#53b9e8" },
];

export default function LayerPanel() {
  const [open, setOpen] = useState(true);
  const {
    activeLayers, toggleLayer,
    choroplethMetric, setChoroplethMetric,
    spatialUnit, setSpatialUnit,
    selectedYear, setYear,
  } = useMapStore();

  const { data: metrics = [] } = useQuery<string[]>("metrics", () => fetchMetrics(), {
    staleTime: 300_000,
  });

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
                      <option value="city">Gesamtstadt</option>
                    </select>
                  </div>
                  <div>
                    <p className="hud-label mb-1.5">Jahr</p>
                    <input
                      type="number"
                      value={selectedYear ?? ""}
                      onChange={(e) => setYear(e.target.value ? parseInt(e.target.value) : null)}
                      placeholder="alle"
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
