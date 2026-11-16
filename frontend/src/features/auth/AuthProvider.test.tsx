import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { getMe } from "@/features/auth/api";
import { tokenStore } from "@/features/auth/session";
import { apiError, ME, mockApi, ok, signedInApi, signedOutApi, TOKEN } from "@/test/mock-api";
import { renderApp } from "@/test/render";

describe("AuthProvider", () => {
  it("restores a session from the refresh cookie and loads the current user", async () => {
    const api = mockApi(signedInApi());
    renderApp("/account");

    expect(await screen.findByRole("heading", { name: "Your account" })).toBeInTheDocument();
    expect(screen.getAllByText("Amina Nakato").length).toBeGreaterThan(0);
    expect(tokenStore.get()).toBe(TOKEN.access_token);
    expect(api.callsTo("GET /me")[0]?.headers.get("Authorization")).toBe(`Bearer ${TOKEN.access_token}`);
    expect(window.localStorage.getItem("access_token")).toBeNull();
  });

  it("calls the refresh endpoint exactly once on load", async () => {
    const api = mockApi(signedInApi());
    renderApp("/account");
    await screen.findByRole("heading", { name: "Your account" });
    expect(api.callsTo("POST /auth/refresh")).toHaveLength(1);
  });

  it("treats a failed refresh as signed out", async () => {
    mockApi(signedOutApi());
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Register" })).toBeInTheDocument();
  });

  it("signs out: calls the API, forgets the token and returns to the signed-out UI", async () => {
    const api = mockApi(signedInApi());
    renderApp("/account");
    await screen.findByRole("heading", { name: "Your account" });

    await userEvent.setup().click(screen.getAllByRole("button", { name: "Sign out" })[0]!);

    await waitFor(() => expect(tokenStore.get()).toBeNull());
    expect(api.callsTo("POST /auth/logout")).toHaveLength(1);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument(); // guard redirect
  });

  it("signs out locally even when the server cannot be reached", async () => {
    mockApi({ ...signedInApi(), "POST /auth/logout": () => apiError(503, "service_unavailable") });
    renderApp("/account");
    await screen.findByRole("heading", { name: "Your account" });
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Sign out" })[0]!);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(tokenStore.get()).toBeNull();
  });

  it("drops to signed-out when the session expires mid-use", async () => {
    let refreshCalls = 0;
    let meCalls = 0;
    mockApi({
      "POST /auth/refresh": () => (++refreshCalls === 1 ? ok(TOKEN) : apiError(401, "invalid_refresh_token")),
      "GET /me": () => (++meCalls === 1 ? ok(ME) : apiError(401, "invalid_token")),
    });
    renderApp("/account");
    await screen.findByRole("heading", { name: "Your account" });

    // A later authenticated call gets 401, the refresh is refused, so the UI must sign the user out.
    await act(async () => {
      await getMe().catch(() => undefined);
    });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(tokenStore.get()).toBeNull();
  });
});
