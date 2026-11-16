import { afterEach, describe, expect, it } from "vitest";
import { setAuthHandler } from "@/lib/api/client";
import { installAuthHandler, refreshSession, tokenStore } from "@/features/auth/session";
import { apiError, mockApi, ok, TOKEN } from "@/test/mock-api";

afterEach(() => setAuthHandler(null));

describe("refreshSession", () => {
  it("stores the new access token in memory only", async () => {
    mockApi({ "POST /auth/refresh": () => ok(TOKEN) });
    await expect(refreshSession()).resolves.toBe("access-token-1");
    expect(tokenStore.get()).toBe("access-token-1");
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });

  it("shares one request between concurrent callers (refresh tokens are single use)", async () => {
    const api = mockApi({ "POST /auth/refresh": () => ok(TOKEN) });
    const results = await Promise.all([refreshSession(), refreshSession(), refreshSession()]);
    expect(results).toEqual(["access-token-1", "access-token-1", "access-token-1"]);
    expect(api.callsTo("POST /auth/refresh")).toHaveLength(1);
  });

  it("returns null and clears the token when the session is gone", async () => {
    tokenStore.set("stale");
    mockApi({ "POST /auth/refresh": () => apiError(401, "invalid_refresh_token") });
    await expect(refreshSession()).resolves.toBeNull();
    expect(tokenStore.get()).toBeNull();
  });

  it("rethrows transient failures instead of pretending the user signed out", async () => {
    mockApi({ "POST /auth/refresh": () => apiError(503, "service_unavailable") });
    await expect(refreshSession()).rejects.toMatchObject({ status: 503 });
  });

  it("sends no Authorization header on refresh", async () => {
    tokenStore.set("old");
    installAuthHandler();
    const api = mockApi({ "POST /auth/refresh": () => ok(TOKEN) });
    await refreshSession();
    expect(api.calls[0]?.headers.get("Authorization")).toBeNull();
  });
});
