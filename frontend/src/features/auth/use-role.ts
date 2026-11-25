/**
 * Derives the user's primary role from their role assignments returned by /me.
 *
 * Priority order: ADMIN > RESOURCE_PROVIDER > PRINTING_OPERATOR > STUDENT.
 * This matches how the backend assigns permissions: an ADMIN gets the highest access,
 * while STUDENT is the default if no elevated role is found.
 *
 * Uses the ROLES array from the /me response — never inferred from permissions alone.
 * This ensures the UI matches the actual role grant, not an incidental permission.
 */
import { useAuth } from "@/features/auth/auth-context";

export type PrimaryRole =
  | "ADMIN"
  | "RESOURCE_PROVIDER"
  | "PRINTING_OPERATOR"
  | "STUDENT"
  | null; // null while loading or unauthenticated

const PRIORITY: PrimaryRole[] = [
  "ADMIN",
  "RESOURCE_PROVIDER",
  "PRINTING_OPERATOR",
  "STUDENT",
];

/** Returns the authenticated user's primary role, or null while loading / unauthenticated. */
export function useRole(): PrimaryRole {
  const { state } = useAuth();
  if (state.status !== "authenticated") return null;

  const roleNames = new Set(state.me.roles.map((r) => r.role));
  for (const role of PRIORITY) {
    if (roleNames.has(role!)) return role;
  }
  return "STUDENT"; // fallback: treat any authenticated user without a recognized role as a student
}

/** Returns the dashboard path for a given role (used for post-login redirect). */
export function roleDashboardPath(role: PrimaryRole): string {
  switch (role) {
    case "ADMIN":
      return "/admin";
    case "RESOURCE_PROVIDER":
      return "/provider/dashboard";
    case "PRINTING_OPERATOR":
      return "/operator/dashboard";
    default:
      return "/dashboard";
  }
}
