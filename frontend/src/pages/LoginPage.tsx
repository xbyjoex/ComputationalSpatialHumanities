import { useState, FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AlertCircle } from "lucide-react";
import { useAuthStore } from "../store/authStore";
import Reticle from "../components/chrome/Reticle";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch {
      setError("Zugang verweigert — ungültige Anmeldedaten");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="blueprint-bg scanlines vignette relative flex min-h-screen items-center justify-center overflow-hidden">
      {/* Watermark reticle */}
      <Reticle className="pointer-events-none absolute -bottom-40 -right-40 h-[560px] w-[560px] text-gotham-750/60" />

      <div className="relative z-10 w-full max-w-sm animate-rise">
        {/* Wordmark */}
        <div className="mb-6 flex flex-col items-center">
          <Reticle className="mb-4 h-12 w-12 text-signal-cyan" />
          <h1 className="font-display text-xl font-bold uppercase tracking-[0.34em] text-gotham-100">
            Auerbachs Auge
          </h1>
          <p className="mt-2 font-mono text-[9px] uppercase tracking-[0.32em] text-gotham-400">
            Leipzig Urban Intelligence
          </p>
        </div>

        <div className="panel corners p-7">
          <p className="hud-label mb-5 border-b border-gotham-700 pb-3 text-center text-signal-cyan">
            Zugang // Authentifizierung
          </p>

          {error && (
            <div
              className="mb-4 flex items-center gap-2 border border-signal-red/50 bg-signal-red/10 px-3 py-2.5 font-mono text-[11px] text-signal-red"
              style={{ borderRadius: 2 }}
            >
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="hud-label mb-1.5 block">Kennung / E-Mail</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="field"
                placeholder="operator@leipzig.de"
              />
            </div>

            <div>
              <label className="hud-label mb-1.5 block">Passwort</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="field"
                placeholder="••••••••"
              />
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? "Authentifiziere …" : "▸ Zugang anfordern"}
            </button>
          </form>
        </div>

        <p className="mt-5 text-center font-mono text-[10px] uppercase tracking-[0.16em] text-gotham-500">
          Keine Kennung?{" "}
          <Link to="/signup" className="text-signal-cyan hover:text-signal-bright">
            Registrieren →
          </Link>
        </p>
      </div>
    </div>
  );
}
