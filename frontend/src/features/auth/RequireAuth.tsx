import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Card } from "@/components/ui/Card";
import { useAuth } from "@/features/auth/auth-context";

/** Route guard: UX only. The API enforces authentication and permissions independently. */
export function RequireAuth() {
  const { state } = useAuth();
  const location = useLocation();

  if (state.status === "loading") {
    return (
      <p role="status" className="text-fg-muted">
        Loading your account…
      </p>
    );
  }
  if (state.status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}

export function RequirePermission({
  permission,
  children,
}: {
  permission: string;
  children: ReactNode;
}) {
  const { can } = useAuth();
  if (!can(permission)) {
    return (
      <Card>
        <h1 className="text-2xl font-extrabold">Access denied</h1>
        <p className="mt-2 text-fg-muted">You don't have permission to view this page.</p>
      </Card>
    );
  }
  return <>{children}</>;
}
