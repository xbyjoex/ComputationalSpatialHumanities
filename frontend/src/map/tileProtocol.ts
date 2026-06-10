import maplibregl from "maplibre-gl";
import { create } from "zustand";
import { useAuthStore } from "../store/authStore";

/**
 * Eigenes Tile-Protokoll (leipzig://) statt transformRequest:
 * - hängt das JWT an jeden Kachel-Request
 * - zählt laufende/abgeschlossene/fehlgeschlagene Requests für die
 *   Fortschrittsanzeige im HUD (MapLibre selbst exponiert keinen Zähler)
 * - 204 (leere Kachel) wird als leere Kachel statt als Fehler behandelt
 */

interface TileLoadState {
  inflight: number;
  /** Kacheln seit Beginn des aktuellen Ladevorgangs (inkl. laufender). */
  total: number;
  done: number;
  errors: number;
  start: () => void;
  finish: (status: "ok" | "error" | "aborted") => void;
}

export const useTileLoadStore = create<TileLoadState>((set) => ({
  inflight: 0,
  total: 0,
  done: 0,
  errors: 0,
  start: () =>
    set((s) =>
      s.inflight === 0
        ? { inflight: 1, total: 1, done: 0, errors: 0 } // neuer Ladevorgang
        : { inflight: s.inflight + 1, total: s.total + 1 }
    ),
  finish: (status) =>
    set((s) => ({
      inflight: Math.max(0, s.inflight - 1),
      done: status === "ok" ? s.done + 1 : s.done,
      errors: status === "error" ? s.errors + 1 : s.errors,
      // Abgebrochene Requests (Pan/Zoom weiter) aus dem Soll herausrechnen
      total: status === "aborted" ? Math.max(1, s.total - 1) : s.total,
    })),
}));

export const TILE_PROTOCOL = "leipzig";

let registered = false;

export function registerTileProtocol(): void {
  if (registered) return;
  registered = true;

  maplibregl.addProtocol(TILE_PROTOCOL, async (params, abortController) => {
    const url = params.url.replace(
      new RegExp(`^${TILE_PROTOCOL}://`),
      `${window.location.origin}/`
    );
    const { start, finish } = useTileLoadStore.getState();
    start();
    try {
      const token = useAuthStore.getState().accessToken;
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        signal: abortController.signal,
      });
      if (res.status === 204) {
        finish("ok");
        return { data: new ArrayBuffer(0) };
      }
      if (!res.ok) {
        finish("error");
        throw new Error(`Kachel ${res.status}`);
      }
      const data = await res.arrayBuffer();
      finish("ok");
      return { data };
    } catch (err) {
      if (abortController.signal.aborted) {
        finish("aborted");
      } else if (!(err instanceof Error && err.message.startsWith("Kachel"))) {
        finish("error");
      }
      throw err;
    }
  });
}
