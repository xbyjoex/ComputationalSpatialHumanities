import { useEffect, useState } from "react";
import { useQuery } from "react-query";
import clsx from "clsx";
import { fetchDatasetStatus } from "../../api/map";

type StatusRow = {
  id: string;
  schedule: string;
  last_run_status: string | null;
  last_run_at: string | null;
};

const two = (n: number) => String(n).padStart(2, "0");

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

export default function StatusBar() {
  const now = useClock();
  const { data: status = [] } = useQuery<StatusRow[]>(
    "datasetStatus",
    fetchDatasetStatus,
    { refetchInterval: 60_000, staleTime: 30_000 }
  );

  const total = status.length;
  const live = status.filter((s) => s.schedule === "live").length;
  const failed = status.filter((s) => s.last_run_status === "failed").length;
  const running = status.filter((s) => s.last_run_status === "started").length;
  const degraded = failed > 0;

  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 overflow-hidden border-t border-gotham-700 bg-gotham-850 px-3 font-mono text-[10px] uppercase tracking-[0.12em] text-gotham-400">
      <span className="flex items-center gap-1.5">
        <span
          className={clsx(
            "led animate-led",
            degraded ? "bg-signal-amber" : "bg-signal-green"
          )}
        />
        <span className={degraded ? "text-signal-amber" : "text-signal-green"}>
          {degraded ? "System eingeschränkt" : "System bereit"}
        </span>
      </span>

      <span className="hidden h-3 w-px bg-gotham-700 sm:block" />

      <span className="hidden sm:inline">
        Quellen <b className="font-semibold text-gotham-200">{total || "–"}</b>
      </span>
      <span className="hidden sm:inline">
        Live <b className="font-semibold text-signal-bright">{live}</b>
      </span>
      {running > 0 && (
        <span className="text-signal-amber">ETL läuft ({running})</span>
      )}
      <span className={failed > 0 ? "text-signal-red" : "hidden sm:inline"}>
        Fehler <b className="font-semibold">{failed}</b>
      </span>

      <span className="flex-1" />

      <span className="hidden md:inline text-gotham-500">
        51.3397°N&nbsp;&nbsp;12.3731°E&nbsp;&nbsp;·&nbsp;&nbsp;Leipzig
      </span>
      <span className="hidden h-3 w-px bg-gotham-700 md:block" />
      <span className="text-gotham-300">
        {two(now.getUTCHours())}:{two(now.getUTCMinutes())}:{two(now.getUTCSeconds())}
        <span className="text-gotham-500">Z</span>
      </span>
    </footer>
  );
}
