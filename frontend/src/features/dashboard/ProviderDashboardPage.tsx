/**
 * Route entry point for /provider/dashboard.
 * Protected by RequirePermission("resource:create").
 */
import { ProviderDashboard } from "@/features/dashboard/ProviderDashboard";

export function ProviderDashboardPage() {
  return <ProviderDashboard />;
}
