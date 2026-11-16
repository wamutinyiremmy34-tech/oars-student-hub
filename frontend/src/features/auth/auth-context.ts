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
   * UX only: decides what to show. The API re-checks every permission on every request,
   * so hiding a button is never a security control.
   */
  can(permission: string, institutionId?: string | null): boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
