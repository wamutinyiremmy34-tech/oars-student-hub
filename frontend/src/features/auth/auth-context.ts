import { createContext, useContext } from "react";
import type { Me } from "@/features/auth/api";

export type AuthState =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | { status: "authenticated"; me: Me };

export interface AuthContextValue {
  state: AuthState;
  signIn(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  /**
   * Refresh the /me data in the auth state (call after a profile update).
   */
  refreshMe(): Promise<void>;
  /**
   * UX only: decides what to show. The API re-checks every permission on every request,
   * so hiding a button is never a security control.
   *
   * Returns true only when the user holds `permission` at the platform level (institution_id null)
   * or at the given `institutionId`. Pass `institutionId` to check an institution-scoped grant.
   */
  can(permission: string, institutionId?: string | null): boolean;
  /**
   * UX only: returns true if the user holds `permission` in ANY scope (platform-wide or
   * institution-scoped). Use this for route guards and nav visibility where the specific
   * institution doesn't matter — the backend enforces the actual scope on the API call.
   */
  canAny(permission: string): boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
