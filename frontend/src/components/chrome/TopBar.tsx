import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { LogOut } from "lucide-react";
import clsx from "clsx";
import { useAuthStore } from "../../store/authStore";
import Reticle from "./Reticle";

const MODULES = [
  { to: "/", code: "01", label: "Lagebild" },
  { to: "/stats", code: "02", label: "Analyse" },
  { to: "/datasets", code: "03", label: "Datenbestand" },
];

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

const two = (n: number) => String(n).padStart(2, "0");

export default function TopBar() {
  const { pathname } = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const now = useClock();

  const isActive = (to: string) =>
    to === "/" ? pathname === "/" : pathname.startsWith(to);

  return (
    <header className="flex h-12 shrink-0 items-stretch border-b border-gotham-700 bg-gotham-850">
      {/* Wordmark */}
      <Link
        to="/"
        className="flex items-center gap-3 border-r border-gotham-700 px-4 transition-colors hover:bg-gotham-800"
      >
        <Reticle className="h-6 w-6 text-signal-cyan" />
        <div className="leading-none">
          <p className="font-display text-sm font-bold uppercase tracking-[0.28em] text-gotham-100">
            Auerbachs Auge
          </p>
          <p className="mt-1 font-mono text-[8.5px] uppercase tracking-[0.3em] text-gotham-400">
            Leipzig Urban Intelligence
          </p>
        </div>
      </Link>

      {/* Module tabs */}
      <nav className="flex items-stretch">
        {MODULES.map(({ to, code, label }) => {
          const active = isActive(to);
          return (
            <Link
              key={to}
              to={to}
              className={clsx(
                "relative flex items-center gap-2 border-r border-gotham-700 px-5 font-display text-xs font-semibold uppercase tracking-[0.18em] transition-colors",
                active
                  ? "bg-gotham-800 text-gotham-100"
                  : "text-gotham-400 hover:bg-gotham-800/60 hover:text-gotham-200"
              )}
            >
              <span
                className={clsx(
                  "led",
                  active ? "animate-led bg-signal-cyan" : "bg-gotham-600"
                )}
              />
              <span className="font-mono text-[9px] text-gotham-500">{code}</span>
              {label}
              {active && (
                <span className="absolute inset-x-0 top-0 h-px bg-signal-cyan" />
              )}
            </Link>
          );
        })}
      </nav>

      <div className="flex-1" />

      {/* Clock */}
      <div className="hidden items-center gap-3 border-l border-gotham-700 px-4 font-mono text-[11px] sm:flex">
        <span className="text-gotham-400">
          {now.getFullYear()}-{two(now.getMonth() + 1)}-{two(now.getDate())}
        </span>
        <span className="tracking-widest text-signal-bright">
          {two(now.getHours())}:{two(now.getMinutes())}:{two(now.getSeconds())}
        </span>
        <span className="text-[9px] uppercase text-gotham-500">lokal</span>
      </div>

      {/* Operator */}
      <div className="flex items-center gap-3 border-l border-gotham-700 px-4">
        <div
          title={user?.email ?? ""}
          className="flex h-7 w-7 items-center justify-center border border-gotham-600 bg-gotham-800 font-mono text-[11px] font-semibold uppercase text-signal-cyan"
        >
          {user?.email?.[0] ?? "?"}
        </div>
        <button
          title="Abmelden"
          onClick={logout}
          className="text-gotham-500 transition-colors hover:text-signal-red"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
