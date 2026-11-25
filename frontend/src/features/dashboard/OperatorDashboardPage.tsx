/**
 * Route entry point for /operator/dashboard.
 * Protected by RequirePermission("order:read_any").
 */
import { OperatorDashboard } from "@/features/dashboard/OperatorDashboard";

export function OperatorDashboardPage() {
  return <OperatorDashboard />;
}
