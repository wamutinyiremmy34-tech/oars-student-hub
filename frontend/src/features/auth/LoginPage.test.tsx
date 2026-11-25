import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { tokenStore } from "@/features/auth/session";
import {
  apiError,
  DASHBOARD,
  ME,
  ME_ADMIN,
  ME_OPERATOR,
  ME_PROVIDER,
  mockApi,
  ok,
  okPage,
  signedOutApi,
  TOKEN,
} from "@/test/mock-api";
import { renderApp } from "@/test/render";

async function fillAndSubmit(email: string, password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginPage", () => {
  it("validates input in the browser without calling the API", async () => {
    const api = mockApi(signedOutApi());
    renderApp("/login");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
    expect(api.callsTo("POST /auth/login")).toHaveLength(0);
  });

  it("redirects a student to /dashboard after login", async () => {
    const api = mockApi({
      ...signedOutApi(),
      "POST /auth/login": () => ok(TOKEN),
      "GET /me": () => ok(ME),
      "GET /dashboard": () => ok(DASHBOARD),
    });
    renderApp("/login");
    await fillAndSubmit("student@demo.oars.dev", "Demo-password-123");

    // Student dashboard heading
    expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(api.callsTo("POST /auth/login")[0]?.body).toMatchObject({ email: "student@demo.oars.dev" });
    expect(tokenStore.get()).toBe(TOKEN.access_token);
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(TOKEN.access_token);
  });

  it("redirects a resource provider to /provider/dashboard after login", async () => {
    mockApi({
      ...signedOutApi(),
      "POST /auth/login": () => ok(TOKEN),
      "GET /me": () => ok(ME_PROVIDER),
      "GET /dashboard": () => ok(DASHBOARD),
      "GET /resources/mine": () => okPage([]),
    });
    renderApp("/login");
    await fillAndSubmit("provider@demo.oars.dev", "Demo-password-123");
    expect(await screen.findByText(/Resource Provider/i)).toBeInTheDocument();
  });

  it("redirects a printing operator to /operator/dashboard after login", async () => {
    mockApi({
      ...signedOutApi(),
      "POST /auth/login": () => ok(TOKEN),
      "GET /me": () => ok(ME_OPERATOR),
      "GET /operator/orders": () => okPage([]),
    });
    renderApp("/login");
    await fillAndSubmit("operator@demo.oars.dev", "Demo-password-123");
    expect(await screen.findByText(/Printing Operator/i)).toBeInTheDocument();
  });

  it("redirects an admin directly to /admin after login", async () => {
    mockApi({
      ...signedOutApi(),
      "POST /auth/login": () => ok(TOKEN),
      "GET /me": () => ok(ME_ADMIN),
      "GET /analytics": () =>
        ok({
          total_users: 10,
          total_resources: 5,
          published_resources: 3,
          total_orders: 2,
          completed_orders: 1,
          total_impressions: 100,
          total_clicks: 10,
        }),
      "GET /dashboard": () => ok(DASHBOARD),
    });
    renderApp("/login");
    await fillAndSubmit("admin@demo.oars.dev", "Demo-password-123");
    // AdminPage renders with heading "Admin"
    expect(await screen.findByRole("heading", { name: "Admin" })).toBeInTheDocument();
  });

  it("returns to the page the user originally asked for before the role-based default", async () => {
    mockApi({
      ...signedOutApi(),
      "POST /auth/login": () => ok(TOKEN),
      "GET /me": () => ok(ME),
    });
    renderApp("/account"); // protected: bounces to /login with a return path
    await fillAndSubmit("student@demo.oars.dev", "Demo-password-123");
    expect(await screen.findByRole("heading", { name: "Your account" })).toBeInTheDocument();
  });

  it("shows a friendly generic message for bad credentials", async () => {
    mockApi({
      ...signedOutApi(),
      "POST /auth/login": () => apiError(401, "invalid_credentials", "Invalid email or password."),
    });
    renderApp("/login");
    await fillAndSubmit("amina@example.com", "wrong-password-1");

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(tokenStore.get()).toBeNull();
  });

  it("explains a suspended account", async () => {
    mockApi({ ...signedOutApi(), "POST /auth/login": () => apiError(403, "account_suspended") });
    renderApp("/login");
    await fillAndSubmit("amina@example.com", "correct-horse-battery");
    expect(await screen.findByRole("alert")).toHaveTextContent(/suspended/i);
  });

  it("explains connection problems", async () => {
    mockApi(signedOutApi()); // no login handler: the mock fails the request like a dropped connection
    renderApp("/login");
    await fillAndSubmit("amina@example.com", "correct-horse-battery");
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/couldn't reach|offline/i));
  });
});
