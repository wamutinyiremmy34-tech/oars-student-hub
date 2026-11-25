import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import type { Me } from "@/features/auth/api";
import { AuthContext, type AuthContextValue } from "@/features/auth/auth-context";
import { useRole, roleDashboardPath } from "@/features/auth/use-role";
import { ME, ME_ADMIN, ME_OPERATOR, ME_PROVIDER } from "@/test/mock-api";

function wrapper(me: Me) {
  const value: AuthContextValue = {
    state: { status: "authenticated", me },
    signIn: async () => undefined,
    signOut: async () => undefined,
    refreshMe: async () => undefined,
    can: () => false,
    canAny: () => false,
  };
  return ({ children }: { children: ReactNode }) =>
    createElement(AuthContext.Provider, { value }, children);
}

function unauthenticatedWrapper() {
  const value: AuthContextValue = {
    state: { status: "unauthenticated" },
    signIn: async () => undefined,
    signOut: async () => undefined,
    refreshMe: async () => undefined,
    can: () => false,
    canAny: () => false,
  };
  return ({ children }: { children: ReactNode }) =>
    createElement(AuthContext.Provider, { value }, children);
}

describe("useRole", () => {
  it("returns STUDENT for a user with the STUDENT role", () => {
    const { result } = renderHook(() => useRole(), { wrapper: wrapper(ME) });
    expect(result.current).toBe("STUDENT");
  });

  it("returns RESOURCE_PROVIDER for a provider", () => {
    const { result } = renderHook(() => useRole(), { wrapper: wrapper(ME_PROVIDER) });
    expect(result.current).toBe("RESOURCE_PROVIDER");
  });

  it("returns PRINTING_OPERATOR for an operator", () => {
    const { result } = renderHook(() => useRole(), { wrapper: wrapper(ME_OPERATOR) });
    expect(result.current).toBe("PRINTING_OPERATOR");
  });

  it("returns ADMIN for an admin", () => {
    const { result } = renderHook(() => useRole(), { wrapper: wrapper(ME_ADMIN) });
    expect(result.current).toBe("ADMIN");
  });

  it("returns null when unauthenticated", () => {
    const { result } = renderHook(() => useRole(), { wrapper: unauthenticatedWrapper() });
    expect(result.current).toBeNull();
  });

  it("prioritises ADMIN over other roles when a user has multiple", () => {
    const multiRole: Me = {
      ...ME,
      roles: [
        { role: "STUDENT", institution_id: "i-1" },
        { role: "ADMIN", institution_id: null },
      ],
    };
    const { result } = renderHook(() => useRole(), { wrapper: wrapper(multiRole) });
    expect(result.current).toBe("ADMIN");
  });
});

describe("roleDashboardPath", () => {
  it("maps STUDENT → /dashboard", () => {
    expect(roleDashboardPath("STUDENT")).toBe("/dashboard");
  });

  it("maps RESOURCE_PROVIDER → /provider/dashboard", () => {
    expect(roleDashboardPath("RESOURCE_PROVIDER")).toBe("/provider/dashboard");
  });

  it("maps PRINTING_OPERATOR → /operator/dashboard", () => {
    expect(roleDashboardPath("PRINTING_OPERATOR")).toBe("/operator/dashboard");
  });

  it("maps ADMIN → /admin", () => {
    expect(roleDashboardPath("ADMIN")).toBe("/admin");
  });

  it("maps null → /dashboard (default for unauthenticated/loading)", () => {
    expect(roleDashboardPath(null)).toBe("/dashboard");
  });
});
