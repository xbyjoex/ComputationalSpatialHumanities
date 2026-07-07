import { useQuery } from "react-query";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { apiClient } from "../../api/client";
import { SONSTIGE_COLOR } from "../../api/elections";

interface ElectionSummary {
  election: {
    election_id: string;
    title: string;
    vote_mode: "erst_zweit" | "single" | "kommunal";
    year: number;
  };
  turnout_pct: number | null;
  parties: Array<{
    party: string;
    erststimmen: number | null;
    zweitstimmen: number | null;
    anteil_pct: number | null;
    party_color: string | null;
  }>;
}

function voteLabel(mode: ElectionSummary["election"]["vote_mode"]): string {
  if (mode === "erst_zweit") return "Zweitstimmen";
  if (mode === "kommunal") return "Stimmen (3 je Wähler:in)";
  return "Stimmen";
}

/** Stadtweites Ergebnis der semantisch zusammengeführten Wahl-Domäne. */
export default function ElectionResultsPanel({ electionId }: { electionId: string }) {
  const { data, isLoading } = useQuery<ElectionSummary>(
    ["election-summary", electionId],
    () => apiClient.get(`/elections/${electionId}/summary`).then((r) => r.data),
    { staleTime: 3_600_000 }
  );

  if (isLoading) {
    return (
      <p className="p-6 text-center font-mono text-xs text-gotham-500">
        <span className="led mr-2 inline-block animate-led bg-signal-cyan" />
        Lade Wahlergebnis …
      </p>
    );
  }
  if (!data || data.parties.length === 0) {
    return (
      <p className="p-6 text-center font-mono text-xs text-gotham-500">
        Stadtergebnis noch nicht geladen (Nightly-ETL abwarten).
      </p>
    );
  }

  const relevant = data.parties.filter((p) => (p.anteil_pct ?? 0) >= 1);
  const chartData = relevant.map((p) => ({
    name: p.party,
    Anteil: p.anteil_pct ?? 0,
    party_color: p.party_color,
  }));

  return (
    <div className="p-4">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-5 gap-y-1 font-mono text-[11px]">
        <span>
          <span className="text-gotham-500">Wahl&nbsp;</span>
          <span className="text-gotham-100">{data.election.title}</span>
        </span>
        {data.turnout_pct != null && (
          <span>
            <span className="text-gotham-500">Wahlbeteiligung&nbsp;</span>
            <span className="font-semibold text-signal-bright">{data.turnout_pct}%</span>
          </span>
        )}
        <span className="text-gotham-500">
          {voteLabel(data.election.vote_mode)} · Parteien ≥ 1%
        </span>
      </div>
      <ResponsiveContainer width="100%" height={Math.max(140, chartData.length * 30)}>
        <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 36, bottom: 0, left: 8 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#1c2c39" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: "#5d7a8d", fontSize: 9, fontFamily: "monospace" }}
            unit="%"
          />
          <YAxis
            type="category"
            dataKey="name"
            width={100}
            tick={{ fill: "#8aa7ba", fontSize: 10, fontFamily: "monospace" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(83,185,232,0.08)" }}
            formatter={(v) => [`${v}%`, "Anteil"]}
            contentStyle={{
              background: "#0c141a",
              border: "1px solid #273d4f",
              fontFamily: "monospace",
              fontSize: 11,
            }}
            labelStyle={{ color: "#8aa7ba" }}
          />
          <Bar dataKey="Anteil" barSize={16} isAnimationActive={false}>
            {chartData.map((d) => (
              <Cell key={d.name} fill={d.party_color ?? SONSTIGE_COLOR} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
