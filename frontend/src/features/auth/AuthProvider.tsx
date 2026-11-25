import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { getMe, login, logout } from "@/features/auth/api";
import { AuthContext, type AuthContextValue, type AuthState } from "@/features/auth/auth-context";
import {
  installAuthHandler,
  onSessionExpired,
  refreshSession,
  tokenStore,
} from "@/features/auth/session";

installAuthHandler();

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading" });

  // Restore the session on load from the HttpOnly refresh cookie. No credentials live in JS storage.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await refreshSession();
        if (!token) {
          if (!cancelled) setState({ status: "unauthenticated" });
          return;
        }
        const me = await getMe();
        if (!cancelled) setState({ status: "authenticated", me });
      } catch {
        if (!cancelled) setState({ status: "unauthenticated" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // If a refresh fails mid-session, drop to the signed-out state instead of leaving a broken UI.
  useEffect(() => {
    onSessionExpired(() => {
      queryClient.clear();
      setState({ status: "unauthenticated" });
    });
    return () => onSessionExpired(null);
  }, [queryClient]);

  const signIn = useCallback(async (email: string, password: string) => {
    const issued = await login(email, password);
    tokenStore.set(issued.access_token);
    try {
      setState({ status: "authenticated", me: await getMe() });
    } catch (error) {
      tokenStore.set(null);
      throw error;
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await logout();
    } catch {
      // Even if the server is unreachable, forget the session locally.
    } finally {
      tokenStore.set(null);
      queryClient.clear();
      setState({ status: "unauthenticated" });
    }
  }, [queryClient]);

  const refreshMe = useCallback(async () => {
    try {
      const me = await getMe();
      setState({ status: "authenticated", me });
    } catch {
      // If refresh fails, leave the state as-is — the user stays signed in.
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      signIn,
      signOut,
      refreshMe,
      can: (permission, institutionId) =>
        state.status === "authenticated" &&
        state.me.permissions.some(
          (grant) =>
            grant.permission === permission &&
            (grant.institution_id === null ||
              (institutionId != null && grant.institution_id === institutionId)),
        ),
      canAny: (permission) =>
        state.status === "authenticated" &&
        state.me.permissions.some((grant) => grant.permission === permission),
    }),
    [state, signIn, signOut, refreshMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
