import { useMapStore, LayerKey } from "../store/mapStore";
import { Layers } from "lucide-react";
import clsx from "clsx";
import { useState } from "react";
import { useQuery } from "react-query";
import { fetchMetrics } from "../api/map";

const LAYERS: { key: LayerKey; label: string; color: string }[] = [
  { key: "park_ride", label: "Park+Ride Auslastung", color: "bg-green-500" },
  { key: "bicycle", label: "Radzählstellen", color: "bg-violet-400" },
  { key: "restrictions", label: "Verkehrseinschränkungen", color: "bg-orange-500" },
  { key: "choropleth", label: "Choropleth", color: "bg-blue-400" },
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
    <div className="absolute top-4 right-4 z-10 w-64">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-sm font-medium text-slate-200 hover:bg-slate-700 transition w-full"
      >
        <Layers className="w-4 h-4 text-brand-400" />
        <span>Ebenen</span>
        <span className="ml-auto text-slate-500">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="mt-2 bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-3 shadow-xl">
          {/* Layer toggles */}
          <div className="space-y-2">
            {LAYERS.map(({ key, label, color }) => (
              <label key={key} className="flex items-center gap-3 cursor-pointer group">
                <div
                  onClick={() => toggleLayer(key)}
                  className={clsx(
                    "w-9 h-5 rounded-full transition-colors relative cursor-pointer",
                    activeLayers.has(key) ? "bg-brand-600" : "bg-slate-600"
                  )}
                >
                  <span
                    className={clsx(
                      "absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow",
                      activeLayers.has(key) ? "translate-x-4" : "translate-x-0.5"
                    )}
                  />
                </div>
                <span className={clsx("w-2 h-2 rounded-full", color)} />
                <span className="text-xs text-slate-300 group-hover:text-white transition">{label}</span>
              </label>
            ))}
          </div>

          {/* Choropleth controls */}
          {activeLayers.has("choropleth") && (
            <div className="pt-3 border-t border-slate-700 space-y-2">
              <p className="text-[10px] text-slate-500 uppercase tracking-wide">Choropleth Metrik</p>
              <select
                value={choroplethMetric}
                onChange={(e) => setChoroplethMetric(e.target.value)}
                className="w-full bg-slate-700 text-slate-200 text-xs rounded-lg px-2 py-1.5 border border-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                <option value="">— Metrik wählen —</option>
                {metrics.map((m: string) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>

              <p className="text-[10px] text-slate-500 uppercase tracking-wide">Raumebene</p>
              <select
                value={spatialUnit}
                onChange={(e) => setSpatialUnit(e.target.value)}
                className="w-full bg-slate-700 text-slate-200 text-xs rounded-lg px-2 py-1.5 border border-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                <option value="ortsteil">Ortsteil</option>
                <option value="stadtbezirk">Stadtbezirk</option>
                <option value="city">Gesamtstadt</option>
              </select>

              <p className="text-[10px] text-slate-500 uppercase tracking-wide">Jahr</p>
              <input
                type="number"
                value={selectedYear ?? ""}
                onChange={(e) => setYear(e.target.value ? parseInt(e.target.value) : null)}
                placeholder="alle Jahre"
                className="w-full bg-slate-700 text-slate-200 text-xs rounded-lg px-2 py-1.5 border border-slate-600 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
