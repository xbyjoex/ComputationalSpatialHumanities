import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";

/** Top-Werte einer kategorialen Spalte als horizontale Balken. */
export default function TopValuesBar({
  top,
  color,
}: {
  top: Array<{ value: string; n: number }>;
  color: string;
}) {
  if (!top.length) return null;
  const data = top.map((t) => ({
    name: String(t.value).slice(0, 28),
    Anzahl: t.n,
  }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(80, data.length * 22)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, bottom: 0, left: 8 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="name"
          width={140}
          tick={{ fill: "#8aa7ba", fontSize: 9, fontFamily: "monospace" }}
          tickLine={false}
          axisLine={false}
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
        <Bar dataKey="Anzahl" fill={color} barSize={12} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
