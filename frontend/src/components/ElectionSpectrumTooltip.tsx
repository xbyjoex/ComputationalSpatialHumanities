import { PieChart, Pie, Cell } from "recharts";
import { SPECTRUM_DOMAIN, SpectrumFeatureProps, SpectrumPartyShare } from "../api/elections";

/** MapLibre serialisiert verschachtelte GeoJSON-Properties als JSON-String. */
export function parseSpectrumProps(raw: Record<string, unknown>): SpectrumFeatureProps {
  let parties: SpectrumPartyShare[] = [];
  if (typeof raw.parties === "string") {
    try {
      const parsed: unknown = JSON.parse(raw.parties);
      if (Array.isArray(parsed)) parties = parsed as SpectrumPartyShare[];
    } catch {
      // fehlerhaftes Property → leere Verteilung statt Crash beim Hovern
    }
  } else if (Array.isArray(raw.parties)) {
    parties = raw.parties as SpectrumPartyShare[];
  }
  return {
    gebiet_code: String(raw.gebiet_code ?? ""),
    name: String(raw.name ?? ""),
    score: typeof raw.score === "number" ? raw.score : null,
    coverage_pct: Number(raw.coverage_pct ?? 0),
    turnout_pct: typeof raw.turnout_pct === "number" ? raw.turnout_pct : null,
    parties,
  };
}

/** Score → Farbe der Rot↔Grau↔Blau-Skala (identisch zur Map-Interpolation). */
export function scoreColor(score: number | null): string {
  if (score === null) return "#6b7683";
  const stops: [number, [number, number, number]][] = [
    [-SPECTRUM_DOMAIN, [229, 72, 77]],   // #e5484d
    [0, [58, 64, 72]],                   // #3a4048
    [SPECTRUM_DOMAIN, [59, 130, 246]],   // #3b82f6
  ];
  const s = Math.max(-SPECTRUM_DOMAIN, Math.min(SPECTRUM_DOMAIN, score));
  const [x0, c0] = s <= 0 ? stops[0] : stops[1];
  const [x1, c1] = s <= 0 ? stops[1] : stops[2];
  const t = (s - x0) / (x1 - x0);
  const rgb = c0.map((v, i) => Math.round(v + t * (c1[i] - v)));
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

export function ElectionTooltipContent({ props }: { props: SpectrumFeatureProps }) {
  const top = props.parties.slice(0, 6);
  return (
    <div className="px-3 py-2">
      <div className="mb-1.5 flex items-center justify-between gap-3 border-b border-gotham-700 pb-1.5">
        <span className="truncate text-[12px] font-medium text-gotham-100">{props.name}</span>
        <span
          className="shrink-0 border px-1.5 py-0.5 font-mono text-[10px]"
          style={{ color: scoreColor(props.score), borderColor: scoreColor(props.score) }}
        >
          {props.score === null ? "–" : props.score.toFixed(2)}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <PieChart width={110} height={110}>
          <Pie
            data={props.parties}
            dataKey="share"
            nameKey="name"
            cx="50%"
            cy="50%"
            innerRadius={26}
            outerRadius={52}
            strokeWidth={0}
            isAnimationActive={false}
          >
            {props.parties.map((p) => (
              <Cell key={p.name} fill={p.color} />
            ))}
          </Pie>
        </PieChart>
        <div className="min-w-0 flex-1 space-y-0.5">
          {top.map((p) => (
            <div key={p.name} className="flex items-center gap-1.5 font-mono text-[10px]">
              <span className="h-1.5 w-1.5 shrink-0" style={{ backgroundColor: p.color }} />
              <span className="min-w-0 flex-1 truncate text-gotham-300">{p.name}</span>
              <span className="text-gotham-100">{p.share.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-1.5 border-t border-gotham-800 pt-1 font-mono text-[9px] text-gotham-500">
        {props.turnout_pct !== null && <>Wahlbeteiligung {props.turnout_pct.toFixed(1)}% · </>}
        {props.coverage_pct.toFixed(0)}% der Stimmen im Score
      </div>
    </div>
  );
}

export default function ElectionSpectrumTooltip({
  hover,
}: {
  hover: { x: number; y: number; props: SpectrumFeatureProps };
}) {
  return (
    <div
      className="pointer-events-none absolute z-20 w-64 border border-gotham-700 bg-gotham-900/95 shadow-xl backdrop-blur-sm"
      style={{
        left: Math.min(hover.x + 14, window.innerWidth - 280),
        top: hover.y + 14,
      }}
    >
      <ElectionTooltipContent props={hover.props} />
    </div>
  );
}
