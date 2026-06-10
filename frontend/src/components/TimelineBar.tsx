import { useMemo } from "react";
import { useQuery } from "react-query";
import { Clock } from "lucide-react";
import clsx from "clsx";
import { useMapStore } from "../store/mapStore";
import { fetchFeatureGroups, FeatureGroup } from "../api/map";

/**
 * Jahres-Timeline für die Datenebene: sichtbar, sobald die Auswahl mehr als
 * ein Jahr abdeckt (z. B. Bundestagswahl 2021/2025). Filtert rein im
 * MapLibre-Style — kein Netzwerk-Refetch beim Scrubben.
 */
export default function TimelineBar() {
  const {
    activeLayers,
    selectedDatasetIds,
    selectedFamilyIds,
    timelineYear,
    setTimelineYear,
  } = useMapStore();

  const { data: groups = [] } = useQuery<FeatureGroup[]>(
    "featureGroups",
    fetchFeatureGroups,
    { staleTime: 600_000, enabled: activeLayers.has("geo_features") }
  );

  const years = useMemo(() => {
    const set = new Set<number>();
    for (const g of groups) {
      const selected = g.is_family
        ? selectedFamilyIds.includes(g.group_id)
        : selectedDatasetIds.includes(g.group_id);
      if (selected) g.years.forEach((y) => set.add(y));
    }
    return [...set].sort((a, b) => a - b);
  }, [groups, selectedDatasetIds, selectedFamilyIds]);

  if (!activeLayers.has("geo_features") || years.length < 2) return null;

  return (
    <div className="absolute bottom-5 left-1/2 z-10 -translate-x-1/2 animate-rise">
      <div className="panel corners flex items-center gap-1 px-3 py-2">
        <Clock className="mr-1.5 h-3.5 w-3.5 shrink-0 text-signal-cyan" />
        <span className="hud-label mr-2 text-gotham-300">Jahr</span>
        <button
          onClick={() => setTimelineYear(null)}
          className={clsx(
            "border px-2 py-0.5 font-mono text-[10px] tracking-wider transition-colors",
            timelineYear === null
              ? "border-signal-cyan bg-signal-cyan/20 text-signal-cyan"
              : "border-gotham-600 text-gotham-400 hover:border-gotham-400 hover:text-gotham-200"
          )}
        >
          Alle
        </button>
        {years.map((y) => (
          <button
            key={y}
            onClick={() => setTimelineYear(timelineYear === y ? null : y)}
            className={clsx(
              "border px-2 py-0.5 font-mono text-[10px] tracking-wider transition-colors",
              timelineYear === y
                ? "border-signal-cyan bg-signal-cyan/20 text-signal-cyan"
                : "border-gotham-600 text-gotham-400 hover:border-gotham-400 hover:text-gotham-200"
            )}
          >
            {y}
          </button>
        ))}
      </div>
    </div>
  );
}
