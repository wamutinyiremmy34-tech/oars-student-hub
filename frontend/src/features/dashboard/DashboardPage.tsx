/**
 * DashboardPage — role-specific dispatcher.
 *
 * This component detects the authenticated user's primary role and renders
 * the appropriate role-specific dashboard component. It is NOT a generic
 * shared dashboard with conditional sections — it is a pure dispatcher.
 *
 * Role → Dashboard mapping:
 *   STUDENT           → StudentDashboard       (at /dashboard)
 *   RESOURCE_PROVIDER → ProviderDashboard      (at /provider/dashboard)
 *   PRINTING_OPERATOR → OperatorDashboard      (at /operator/dashboard)
 *   ADMIN             → AdminDashboard         (the AdminPage at /admin is the full tool;
 *                                               /dashboard for admin redirects there)
 *
 * Each role-specific dashboard is a completely separate component with its own
 * layout, data, navigation, and actions. No shared generic wrapper.
 */
import { Navigate } from "react-router-dom";
import { useAuth } from "@/features/auth/auth-context";
import { useRole } from "@/features/auth/use-role";
import { StudentDashboard } from "@/features/dashboard/StudentDashboard";

/**
 * The /dashboard route: Student dashboard for STUDENT users;
 * redirects to their own workspace for other roles.
 */
export function DashboardPage() {
  const { state } = useAuth();
  const role = useRole();

  if (state.status === "loading") {
    return (
      <p role="status" className="text-fg-muted">
        Loading your dashboard…
      </p>
    );
  }

  if (state.status !== "authenticated") return null;

  // Non-student roles: redirect to their own workspace root
  if (role === "ADMIN") return <Navigate to="/admin" replace />;
  if (role === "RESOURCE_PROVIDER") return <Navigate to="/provider/dashboard" replace />;
  if (role === "PRINTING_OPERATOR") return <Navigate to="/operator/dashboard" replace />;

  // Student (default)
  return <StudentDashboard />;
}
