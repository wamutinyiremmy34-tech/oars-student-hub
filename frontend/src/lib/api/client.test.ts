import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { apiFetch, setAuthHandler } from "@/lib/api/client";
import { ApiError, NetworkError, RequestTimeoutError } from "@/lib/api/errors";

const schema = z.object({ status: z.string() });

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  setAuthHandler(null);
});

describe("apiFetch", () => {
  it("returns validated data from the success envelope", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ data: { status: "ok" }, meta: {} }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/health", { schema })).resolves.toEqual({ status: "ok" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/health");
    expect(init.credentials).toBe("include");
    expect(init.method).toBe("GET");
  });

  it("converts error envelopes into ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: "not_found", message: "Nope", details: null, request_id: "r-1" } },
          404,
        ),
      ),
    );
    const error = await apiFetch("/x", { schema }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, code: "not_found", requestId: "r-1" });
  });

  it("handles non-JSON error bodies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502 })),
    );
    const error = await apiFetch("/x", { schema }).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 502, code: "http_error" });
  });

  it("rejects responses that do not match the schema", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ data: { wrong: 1 } })));
    const error = await apiFetch("/x", { schema }).catch((e: unknown) => e);
    expect(error).toMatchObject({ code: "invalid_response" });
  });

  it("maps fetch failures to NetworkError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiFetch("/x", { schema })).rejects.toBeInstanceOf(NetworkError);
  });

  it("aborts and throws RequestTimeoutError after the timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError")),
            );
          }),
      ),
    );
    const assertion = expect(apiFetch("/slow", { schema, timeoutMs: 100 })).rejects.toBeInstanceOf(
      RequestTimeoutError,
    );
    await vi.advanceTimersByTimeAsync(100);
    await assertion;
  });
});

describe("apiFetch authentication", () => {
  const unauthorized = () =>
    jsonResponse({ error: { code: "invalid_token", message: "expired", request_id: "r" } }, 401);

  it("attaches the in-memory access token and never when auth is false", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => jsonResponse({ data: { status: "ok" } }));
    vi.stubGlobal("fetch", fetchMock);
    setAuthHandler({ getAccessToken: () => "tok-1", refresh: async () => null });

    await apiFetch("/me", { schema });
    await apiFetch("/auth/login", { schema, auth: false });

    const sent = fetchMock.mock.calls.map(([, init]) => (init as RequestInit).headers as Record<string, string>);
    expect(sent[0]?.Authorization).toBe("Bearer tok-1");
    expect(sent[1]?.Authorization).toBeUndefined();
  });

  it("refreshes once on 401 and retries with the new token", async () => {
    let token = "old";
    const refresh = vi.fn(async () => {
      token = "new";
      return token;
    });
    setAuthHandler({ getAccessToken: () => token, refresh });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(jsonResponse({ data: { status: "ok" } }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/me", { schema })).resolves.toEqual({ status: "ok" });
    expect(refresh).toHaveBeenCalledOnce();
    const retryHeaders = (fetchMock.mock.calls[1]?.[1] as RequestInit).headers as Record<string, string>;
    expect(retryHeaders.Authorization).toBe("Bearer new");
  });

  it("surfaces the 401 when the session cannot be refreshed", async () => {
    setAuthHandler({ getAccessToken: () => "old", refresh: async () => null });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(unauthorized()));
    const error = await apiFetch("/me", { schema }).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 401, code: "invalid_token" });
  });

  it("does not try to refresh when skipAuthRefresh is set", async () => {
    const refresh = vi.fn(async () => "x");
    setAuthHandler({ getAccessToken: () => null, refresh });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(unauthorized()));
    await apiFetch("/auth/login", { schema, skipAuthRefresh: true }).catch(() => undefined);
    expect(refresh).not.toHaveBeenCalled();
  });
});
