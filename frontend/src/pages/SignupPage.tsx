import { useState, FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AlertCircle, CheckCircle } from "lucide-react";
import { apiClient } from "../api/client";
import axios from "axios";
import Reticle from "../components/chrome/Reticle";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await apiClient.post("/auth/register", {
        email,
        password,
        full_name: fullName || undefined,
      });
      setSuccess(true);
      setTimeout(() => navigate("/login"), 5000);
    } catch (err) {
      if (axios.isAxiosError(err)) {
        const detail = err.response?.data?.detail;
        setError(typeof detail === "string" ? detail : "Registrierung fehlgeschlagen.");
      } else {
        setError("Registrierung fehlgeschlagen.");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="blueprint-bg scanlines vignette relative flex min-h-screen items-center justify-center overflow-hidden">
      <Reticle className="pointer-events-none absolute -bottom-40 -right-40 h-[560px] w-[560px] text-gotham-750/60" />

      <div className="relative z-10 w-full max-w-sm animate-rise">
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
            Zugang // Kennung anlegen
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

          {success && (
            <div
              className="mb-4 flex items-center gap-2 border border-signal-green/50 bg-signal-green/10 px-3 py-2.5 font-mono text-[11px] text-signal-green"
              style={{ borderRadius: 2 }}
            >
              <CheckCircle className="h-3.5 w-3.5 shrink-0" />
              Anfrage gesendet — dein Zugang wartet auf Freigabe. Nach der Freigabe kannst du
              dich anmelden.
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="hud-label mb-1.5 block">Name (optional)</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoComplete="name"
                className="field"
                placeholder="Max Mustermann"
              />
            </div>

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
                minLength={8}
                autoComplete="new-password"
                className="field"
                placeholder="Mindestens 8 Zeichen"
              />
            </div>

            <button type="submit" disabled={loading || success} className="btn-primary w-full">
              {loading ? "Sende Anfrage …" : "▸ Zugang anfragen"}
            </button>
          </form>
        </div>

        <p className="mt-5 text-center font-mono text-[10px] uppercase tracking-[0.16em] text-gotham-500">
          Bereits eine Kennung?{" "}
          <Link to="/login" className="text-signal-cyan hover:text-signal-bright">
            Anmelden →
          </Link>
        </p>
      </div>
    </div>
  );
}
