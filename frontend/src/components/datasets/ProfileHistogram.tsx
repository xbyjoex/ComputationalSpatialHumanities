import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { Histogram } from "../../api/datasets";

function fmtTick(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 10_000) return `${Math.round(v / 1000)}k`;
  if (Number.isInteger(v)) return v.toLocaleString();
  return v.toFixed(1);
}

/** Verteilungs-Histogramm (≤20 Buckets) einer numerischen Spalte. */
export default function ProfileHistogram({
  data,
  color,
}: {
  data: Histogram;
  color: string;
}) {
  if (!data.buckets.length) {
    return (
      <p className="py-4 text-center font-mono text-[10px] text-gotham-500">
        Keine Werte für ein Histogramm.
      </p>
    );
  }
  const chartData = data.buckets.map((b) => ({
    label: fmtTick(b.lo),
    Anzahl: b.n,
  }));
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
        <CartesianGrid strokeDasharray="2 4" stroke="#1c2c39" />
        <XAxis
          dataKey="label"
          tick={{ fill: "#5d7a8d", fontSize: 9, fontFamily: "monospace" }}
          interval="preserveStartEnd"
          tickLine={false}
        />
        <YAxis
          tick={{ fill: "#5d7a8d", fontSize: 9, fontFamily: "monospace" }}
          tickFormatter={fmtTick}
          tickLine={false}
        />
        <Tooltip
          cursor={{ fill: "rgba(83,185,232,0.08)" }}
          contentStyle={{
            background: "#0c141a",
            border: "1px solid #273d4f",
            fontFamily: "monospace",
            fontSize: 11,
          }}
          labelStyle={{ color: "#8aa7ba" }}
        />
        <Bar dataKey="Anzahl" fill={color} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
