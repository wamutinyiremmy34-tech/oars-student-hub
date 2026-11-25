/**
 * Role separation tests.
 *
 * Verifies that each of the four roles receives a genuinely distinct interface:
 * - Correct dashboard heading and role label
 * - Role-specific navigation items present
 * - Navigation items from OTHER roles absent
 * - Correct route protection (unauthorized users blocked)
 * - Post-login redirect goes to the right workspace
 * - Logout clears everything and shows the signed-out UI
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { Me } from "@/features/auth/api";
import { routes } from "@/app/routes";
import { AuthContext, type AuthContextValue } from "@/features/auth/auth-context";
import {
  DASHBOARD,
  ME,
  ME_ADMIN,
  ME_OPERATOR,
  ME_PROVIDER,
  mockApi,
  ok,
  okPage,
  signedInApi,
  signedInAsAdmin,
  signedInAsOperator,
  signedInAsProvider,
  signedOutApi,
} from "@/test/mock-api";
import { renderApp } from "@/test/render";
import { AppProviders } from "@/app/providers";
import { QueryClient } from "@tanstack/react-query";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function renderWithRole(me: Me, path = "/") {
  const permissions = me.permissions.map((p) => p.permission);
  const value: AuthContextValue = {
    state: { status: "authenticated", me },
    signIn: async () => undefined,
    signOut: async () => undefined,
    refreshMe: async () => undefined,
    can: (permission) => permissions.includes(permission),
    canAny: (permission) => permissions.includes(permission),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <AppProviders client={client}>
      <AuthContext.Provider value={value}>
        <RouterProvider router={router} />
      </AuthContext.Provider>
    </AppProviders>,
  );
}

// ─── Navigation isolation tests ───────────────────────────────────────────────

describe("Student navigation", () => {
  it("contains student-specific links", () => {
    mockApi({ "GET /dashboard": () => ok(DASHBOARD) });
    renderWithRole(ME);
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resources" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "My orders" })).toBeInTheDocument();
  });

  it("does NOT contain operator or provider nav links", () => {
    mockApi({ "GET /dashboard": () => ok(DASHBOARD) });
    renderWithRole(ME);
    expect(screen.queryByRole("link", { name: "Print queue" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My resources" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admin dashboard" })).not.toBeInTheDocument();
  });

  it("shows the Student role badge", () => {
    mockApi({ "GET /dashboard": () => ok(DASHBOARD) });
    renderWithRole(ME);
    expect(screen.getByText("Student")).toBeInTheDocument();
  });
});

describe("Resource Provider navigation", () => {
  it("contains provider-specific links", () => {
    renderWithRole(ME_PROVIDER);
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "My resources" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload resource" })).toBeInTheDocument();
  });

  it("does NOT contain student printing links or operator links", () => {
    renderWithRole(ME_PROVIDER);
    expect(screen.queryByRole("link", { name: "Print queue" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My orders" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admin dashboard" })).not.toBeInTheDocument();
  });

  it("shows the Provider role badge", () => {
    renderWithRole(ME_PROVIDER);
    expect(screen.getByText("Provider")).toBeInTheDocument();
  });
});

describe("Printing Operator navigation", () => {
  it("contains operator-specific links", () => {
    mockApi({ "GET /operator/orders": () => okPage([]) });
    renderWithRole(ME_OPERATOR);
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Print queue" })).toBeInTheDocument();
  });

  it("does NOT contain student or provider links", () => {
    mockApi({ "GET /operator/orders": () => okPage([]) });
    renderWithRole(ME_OPERATOR);
    expect(screen.queryByRole("link", { name: "My resources" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My orders" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admin dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "New print order" })).not.toBeInTheDocument();
  });

  it("shows the Operator role badge", () => {
    mockApi({ "GET /operator/orders": () => okPage([]) });
    renderWithRole(ME_OPERATOR);
    expect(screen.getByText("Operator")).toBeInTheDocument();
  });
});

describe("Admin navigation", () => {
  it("contains admin-specific links", () => {
    renderWithRole(ME_ADMIN);
    expect(screen.getByRole("link", { name: "Admin dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Moderation" })).toBeInTheDocument();
  });

  it("does NOT contain student printing or operator queue links", () => {
    renderWithRole(ME_ADMIN);
    expect(screen.queryByRole("link", { name: "New print order" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My orders" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Print queue" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My resources" })).not.toBeInTheDocument();
  });

  it("shows the Admin role badge", () => {
    renderWithRole(ME_ADMIN);
    // The role badge displays "Admin" for the ADMIN role
    const badges = screen.getAllByText("Admin");
    expect(badges.length).toBeGreaterThan(0);
  });
});

// ─── Dashboard routing ────────────────────────────────────────────────────────

describe("Dashboard routing — /dashboard redirects by role", () => {
  it("student stays at /dashboard and sees the Student dashboard", async () => {
    mockApi({ ...signedInApi(), "GET /dashboard": () => ok(DASHBOARD) });
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
  });

  it("provider at /dashboard is redirected to /provider/dashboard", async () => {
    mockApi({
      ...signedInAsProvider(),
      "GET /dashboard": () => ok(DASHBOARD),
      "GET /resources/mine": () => okPage([]),
    });
    renderApp("/dashboard");
    // Provider dashboard shows the "Resource Provider" role label
    expect(await screen.findByText(/Resource Provider/i)).toBeInTheDocument();
  });

  it("operator at /dashboard is redirected to /operator/dashboard", async () => {
    mockApi({
      ...signedInAsOperator(),
      "GET /operator/orders": () => okPage([]),
    });
    renderApp("/dashboard");
    expect(await screen.findByText(/Printing Operator/i)).toBeInTheDocument();
  });

  it("admin at /dashboard is redirected to /admin", async () => {
    mockApi({
      ...signedInAsAdmin(),
      "GET /analytics": () =>
        ok({
          total_users: 10, total_resources: 5, published_resources: 3,
          total_orders: 2, completed_orders: 1, total_impressions: 100, total_clicks: 10,
        }),
      "GET /dashboard": () => ok(DASHBOARD),
    });
    renderApp("/dashboard");
    // Admin is redirected to /admin which renders the AdminPage with heading "Admin"
    expect(await screen.findByRole("heading", { name: "Admin" })).toBeInTheDocument();
  });
});

// ─── Route protection ─────────────────────────────────────────────────────────

describe("Route protection", () => {
  it("unauthenticated users cannot access /dashboard", async () => {
    mockApi(signedOutApi());
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("student cannot access /operator/dashboard (access denied shown)", async () => {
    // Student has no order:read_any
    mockApi(signedInApi());
    renderApp("/operator/dashboard");
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

  it("student cannot access /provider/dashboard", async () => {
    mockApi(signedInApi());
    renderApp("/provider/dashboard");
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

  it("student cannot access /admin", async () => {
    mockApi(signedInApi());
    renderApp("/admin");
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

  it("operator cannot access /admin (no user:read permission)", async () => {
    mockApi(signedInAsOperator());
    renderApp("/admin");
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

  it("provider cannot access /operator/dashboard (no order:read_any)", async () => {
    mockApi(signedInAsProvider());
    renderApp("/operator/dashboard");
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });
});

// ─── Logout ───────────────────────────────────────────────────────────────────

describe("Logout clears role state", () => {
  it("after sign-out, user sees the public nav (Sign in / Register), not role nav", async () => {
    mockApi({ ...signedInApi(), "GET /dashboard": () => ok(DASHBOARD) });
    renderApp("/dashboard");

    // Wait until signed in
    expect(await screen.findByRole("heading", { name: /welcome back/i })).toBeInTheDocument();

    // Sign out
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Sign out" })[0]!);

    // Public nav appears
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByText("Student")).not.toBeInTheDocument();
  });
});
