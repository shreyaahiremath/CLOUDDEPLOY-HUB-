import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, setToken, setUnauthorizedHandler, type User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  signIn: (token: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(() => Boolean(getToken()));

  const load = useCallback(async () => {
    if (!getToken()) { setUser(null); setLoading(false); return; }
    try { setUser(await api<User>("/api/auth/me")); }
    catch { setToken(null); setUser(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    void load();
  }, [load]);

  const value = useMemo<AuthState>(() => ({
    user,
    loading,
    signIn: async (token: string) => { setToken(token); setLoading(true); await load(); },
    signOut: async () => {
      try { await api("/api/auth/logout", { method: "POST" }); } catch { /* already signed out */ }
      setToken(null);
      setUser(null);
    },
  }), [user, loading, load]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
