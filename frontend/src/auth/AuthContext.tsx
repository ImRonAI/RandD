import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AuthUser = {
  user_id: number;
  email: string;
  tenant_id: number | null;
  is_platform_admin: boolean;
};

export type AuthTenant = {
  tenant_id: number;
  name: string;
  slug: string;
} | null;

type AuthState = {
  status: "loading" | "authed" | "anonymous";
  user: AuthUser | null;
  tenant: AuthTenant;
  login: (email: string, password: string) => Promise<{ ok: boolean; error?: string }>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export const useAuth = (): AuthState => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [status, setStatus] = useState<AuthState["status"]>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tenant, setTenant] = useState<AuthTenant>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/auth/me", { credentials: "include" });
      if (res.ok) {
        const data = (await res.json()) as { user: AuthUser; tenant: AuthTenant };
        setUser(data.user);
        setTenant(data.tenant);
        setStatus("authed");
      } else {
        setUser(null);
        setTenant(null);
        setStatus("anonymous");
      }
    } catch {
      setUser(null);
      setTenant(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
          return { ok: false, error: "Invalid email or password." };
        }
        const data = (await res.json()) as { user: AuthUser; tenant: AuthTenant };
        setUser(data.user);
        setTenant(data.tenant);
        setStatus("authed");
        return { ok: true };
      } catch {
        return { ok: false, error: "Could not reach the server." };
      }
    },
    []
  );

  const logout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    } catch {
      // ignore — clearing local state regardless
    }
    setUser(null);
    setTenant(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<AuthState>(
    () => ({ status, user, tenant, login, logout, refresh }),
    [status, user, tenant, login, logout, refresh]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
