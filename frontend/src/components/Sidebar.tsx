import { Link, useLocation } from "react-router-dom";
import { Map, BarChart3, Database, LogOut, MapPin } from "lucide-react";
import { useAuthStore } from "../store/authStore";
import clsx from "clsx";

const navItems = [
  { to: "/", icon: Map, label: "Karte" },
  { to: "/stats", icon: BarChart3, label: "Statistiken" },
  { to: "/datasets", icon: Database, label: "Datensätze" },
];

export default function Sidebar() {
  const { pathname } = useLocation();
  const logout = useAuthStore((s) => s.logout);
  const user = useAuthStore((s) => s.user);

  return (
    <nav className="w-16 flex flex-col items-center py-4 bg-slate-800 border-r border-slate-700 shrink-0">
      {/* Logo */}
      <div className="w-9 h-9 bg-brand-600 rounded-xl flex items-center justify-center mb-6">
        <MapPin className="w-5 h-5 text-white" />
      </div>

      <div className="flex-1 flex flex-col gap-1 w-full px-2">
        {navItems.map(({ to, icon: Icon, label }) => (
          <Link
            key={to}
            to={to}
            title={label}
            className={clsx(
              "flex flex-col items-center gap-1 py-2.5 rounded-xl text-xs font-medium transition-colors",
              pathname === to
                ? "bg-brand-600 text-white"
                : "text-slate-400 hover:text-white hover:bg-slate-700"
            )}
          >
            <Icon className="w-5 h-5" />
            <span className="text-[9px] leading-none">{label}</span>
          </Link>
        ))}
      </div>

      {/* User + logout */}
      <div className="flex flex-col items-center gap-2 mt-4">
        <div
          title={user?.email ?? ""}
          className="w-8 h-8 rounded-full bg-brand-700 flex items-center justify-center text-white text-xs font-bold uppercase"
        >
          {user?.email?.[0] ?? "?"}
        </div>
        <button
          title="Abmelden"
          onClick={logout}
          className="text-slate-500 hover:text-red-400 transition-colors"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </nav>
  );
}
