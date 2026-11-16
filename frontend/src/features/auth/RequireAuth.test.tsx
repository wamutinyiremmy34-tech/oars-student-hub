import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthContext, type AuthContextValue } from "@/features/auth/auth-context";
import { RequirePermission } from "@/features/auth/RequireAuth";
import { ME, mockApi, signedInApi, signedOutApi } from "@/test/mock-api";
import { renderApp } from "@/test/render";

describe("RequireAuth (real providers)", () => {
  it("redirects visitors without a session to the sign-in page", async () => {
    mockApi(signedOutApi());
    renderApp("/account");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Your account" })).not.toBeInTheDocument();
  });

  it("shows a loading state, never protected content, while the session is being restored", () => {
    mockApi({ "POST /auth/refresh": () => new Promise<Response>(() => undefined) }); // never resolves
    renderApp("/account");
    expect(screen.getByRole("status")).toHaveTextContent(/loading/i);
    expect(screen.queryByRole("heading", { name: "Your account" })).not.toBeInTheDocument();
  });

  it("lets signed-in users through", async () => {
    mockApi(signedInApi());
    renderApp("/account");
    expect(await screen.findByRole("heading", { name: "Your account" })).toBeInTheDocument();
  });
});

function withAuth(permissions: string[], ui: ReactElement) {
  const value: AuthContextValue = {
    state: { status: "authenticated", me: { ...ME, permissions: permissions.map((permission) => ({ permission, institution_id: null })) } },
    signIn: async () => undefined,
    signOut: async () => undefined,
    can: (permission) => permissions.includes(permission),
  };
  const router = createMemoryRouter([{ path: "/", element: ui }]);
  return render(
    <AuthContext.Provider value={value}>
      <RouterProvider router={router} />
    </AuthContext.Provider>,
  );
}

describe("RequirePermission", () => {
  it("renders children only when the permission is held", () => {
    withAuth(["user:read"], (
      <RequirePermission permission="user:read">
        <p>secret admin page</p>
      </RequirePermission>
    ));
    expect(screen.getByText("secret admin page")).toBeInTheDocument();
  });

  it("shows access denied otherwise", () => {
    withAuth([], (
      <RequirePermission permission="user:read">
        <p>secret admin page</p>
      </RequirePermission>
    ));
    expect(screen.queryByText("secret admin page")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

});
