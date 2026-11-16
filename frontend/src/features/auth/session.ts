import { z } from "zod";
import { apiFetch, setAuthHandler } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

export const tokenSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  expires_in: z.number(),
});

/** The access token is kept in memory only. It is never written to localStorage or sessionStorage. */
let accessToken: string | null = null;
export const tokenStore = {
  get: () => accessToken,
  set: (token: string | null) => {
    accessToken = token;
  },
};

let inflight: Promise<string | null> | null = null;
let expiredListener: (() => void) | null = null;

export function onSessionExpired(listener: (() => void) | null): void {
  expiredListener = listener;
}

/**
 * Exchanges the HttpOnly refresh cookie for a new access token.
 * Concurrent callers share one request: the server rotates the refresh token on every use and treats
 * a replayed token as theft, so two parallel refreshes (React StrictMode, several 401s at once)
 * must never both hit the server.
 */
export function refreshSession(): Promise<string | null> {
  inflight ??= (async () => {
    try {
      const issued = await apiFetch("/auth/refresh", {
        method: "POST",
        schema: tokenSchema,
        auth: false,
        skipAuthRefresh: true,
      });
      tokenStore.set(issued.access_token);
      return issued.access_token;
    } catch (error) {
      tokenStore.set(null);
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return null;
      throw error;
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

export function installAuthHandler(): void {
  setAuthHandler({
    getAccessToken: () => tokenStore.get(),
    refresh: async () => {
      const token = await refreshSession().catch(() => null);
      if (!token) expiredListener?.();
      return token;
    },
  });
}

/** Test-only: clears the module-level inflight promise so one test's never-resolving
 *  refresh cannot leak into the next test. */
export function __resetInflightForTest(): void {
  inflight = null;
}
