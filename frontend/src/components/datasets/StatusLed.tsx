export default function StatusLed({ s }: { s: string | null }) {
  if (s === "success") return <span className="led bg-signal-green" title="Erfolgreich" />;
  if (s === "failed") return <span className="led bg-signal-red" title="Fehlgeschlagen" />;
  if (s === "started") return <span className="led animate-led bg-signal-amber" title="Läuft" />;
  if (s === "skipped")
    return <span className="led bg-gotham-400" title="Übersprungen — Quelle unverändert" />;
  return <span className="led bg-gotham-600" title="Kein Lauf" />;
}
