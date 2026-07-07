import { useEffect } from "react";
import { useQuery } from "react-query";
import { Vote } from "lucide-react";
import clsx from "clsx";
import { fetchSpectrumOptions, SpectrumOptions } from "../api/elections";
import { useMapStore } from "../store/mapStore";

const LEVEL_LABELS: Record<string, string> = {
  ortsteil: "Ortsteil",
  stadtbezirk: "Stadtbezirk",
  wahlbezirk: "Wahlbezirk",
};

function pickLevel(levels: string[]): string {
  return levels.includes("ortsteil") ? "ortsteil" : levels[0];
}

/** Wahltyp/Jahr/Ebene-Picker für die Politisches-Spektrum-Ebene. */
export default function ElectionsControl() {
  const { activeLayers, setLayer, electionSelection, setElectionSelection } = useMapStore();
  const on = activeLayers.has("elections");

  const { data: options } = useQuery<SpectrumOptions>("spectrumOptions", fetchSpectrumOptions, {
    enabled: on,
    staleTime: 3_600_000,
  });

  // Default: jüngste Bundestagswahl, sobald Optionen da sind
  useEffect(() => {
    if (!on || electionSelection || !options?.elections.length) return;
    const el =
      options.elections.find((e) => e.election_type === "bundestagswahl") ?? options.elections[0];
    const y = el.years[0];
    setElectionSelection({ electionType: el.election_type, year: y.year, level: pickLevel(y.levels) });
  }, [on, options, electionSelection, setElectionSelection]);

  const current = options?.elections.find(
    (e) => e.election_type === electionSelection?.electionType
  );
  const currentYear = current?.years.find((y) => y.year === electionSelection?.year);

  return (
    <div className="mt-3 space-y-2 border-t border-gotham-700 pt-2.5">
      <button
        onClick={() => {
          setLayer("elections", !on);
          if (on) setElectionSelection(null);
        }}
        className="group flex w-full items-center gap-2 px-1 py-1 text-left transition-colors hover:bg-gotham-800/70"
      >
        <span
          className={clsx(
            "flex h-3 w-3 shrink-0 items-center justify-center border transition-colors",
            on ? "border-signal-cyan bg-signal-cyan/20" : "border-gotham-500 group-hover:border-gotham-400"
          )}
        />
        <Vote className="h-3 w-3 shrink-0 text-gotham-500" />
        <span className={clsx("flex-1 text-[11px]", on ? "text-gotham-100" : "text-gotham-400")}>
          Wahlergebnisse (Spektrum)
        </span>
      </button>

      {on && options && electionSelection && (
        <div className="space-y-2 pl-1">
          <select
            value={electionSelection.electionType}
            onChange={(e) => {
              const el = options.elections.find((x) => x.election_type === e.target.value);
              if (!el) return;
              const y = el.years[0];
              setElectionSelection({
                electionType: el.election_type,
                year: y.year,
                level: pickLevel(y.levels),
              });
            }}
            className="field"
          >
            {options.elections.map((e) => (
              <option key={e.election_type} value={e.election_type}>
                {e.title}
              </option>
            ))}
          </select>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={electionSelection.year}
              onChange={(e) => {
                const y = current?.years.find((x) => x.year === Number(e.target.value));
                if (!y) return;
                setElectionSelection({
                  ...electionSelection,
                  year: y.year,
                  level: y.levels.includes(electionSelection.level)
                    ? electionSelection.level
                    : pickLevel(y.levels),
                });
              }}
              className="field"
            >
              {current?.years.map((y) => (
                <option key={y.year} value={y.year}>
                  {y.year}
                </option>
              ))}
            </select>
            <select
              value={electionSelection.level}
              onChange={(e) => setElectionSelection({ ...electionSelection, level: e.target.value })}
              className="field"
            >
              {currentYear?.levels.map((l) => (
                <option key={l} value={l}>
                  {LEVEL_LABELS[l] ?? l}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
