import { create } from "zustand";
import { persist } from "zustand/middleware";
import axios from "axios";

interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_admin: boolean;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,

      login: async (email, password) => {
        const res = await axios.post("/api/auth/login", { email, password });
        const { access_token, refresh_token } = res.data;
        // Fetch user profile
        const me = await axios.get("/api/auth/me", {
          headers: { Authorization: `Bearer ${access_token}` },
        });
        set({ accessToken: access_token, refreshToken: refresh_token, user: me.data });
      },

      logout: () => {
        const rt = get().refreshToken;
        if (rt) {
          axios
            .post(`/api/auth/logout?refresh_token=${encodeURIComponent(rt)}`, null, {
              headers: { Authorization: `Bearer ${get().accessToken}` },
            })
            .catch(() => {});
        }
        set({ accessToken: null, refreshToken: null, user: null });
      },

      refresh: async () => {
        const rt = get().refreshToken;
        if (!rt) throw new Error("No refresh token");
        const res = await axios.post(
          `/api/auth/refresh?refresh_token=${encodeURIComponent(rt)}`
        );
        set({ accessToken: res.data.access_token, refreshToken: res.data.refresh_token });
      },
    }),
    {
      name: "leipzig-auth",
      partialize: (s) => ({ refreshToken: s.refreshToken, user: s.user }),
    }
  )
);
