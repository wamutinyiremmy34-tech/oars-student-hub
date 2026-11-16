import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useAuth } from "@/features/auth/auth-context";
import { getDashboard } from "@/features/dashboard/api";
import { formatUgx } from "@/lib/format";
import { toUserMessage } from "@/lib/api/errors";

function StatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    SUBMITTED: "Submitted",
    ACCEPTED: "Accepted",
    PRINTING: "Printing",
    READY_FOR_PICKUP: "Ready",
    COMPLETED: "Completed",
    CANCELLED: "Cancelled",
    REJECTED: "Rejected",
  };
  const colors: Record<string, string> = {
    READY_FOR_PICKUP: "bg-accent/10 text-accent",
    COMPLETED: "bg-accent/10 text-accent",
    REJECTED: "bg-danger/10 text-danger-strong",
    CANCELLED: "bg-warning/10 text-warning",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${colors[status] ?? "bg-secondary/10 text-secondary"}`}>
      {labels[status] ?? status}
    </span>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-16 rounded-card bg-surface" />
      ))}
    </div>
  );
}

export function DashboardPage() {
  const { state, can } = useAuth();
  const dashQ = useQuery({
    queryKey: ["dashboard"],
    queryFn: ({ signal }) => getDashboard(signal),
    enabled: state.status === "authenticated",
    retry: false,
  });

  if (state.status !== "authenticated") return null;

  if (dashQ.isPending) return <LoadingSkeleton />;
  if (dashQ.isError) {
    return (
      <div className="space-y-4">
        <Alert variant="error">{toUserMessage(dashQ.error)}</Alert>
        <Button variant="secondary" onClick={() => void dashQ.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  const d = dashQ.data;

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <Card className="space-y-3">
        <h1 className="text-2xl font-extrabold">{d.greeting}</h1>
        <div className="flex flex-wrap gap-3">
          {d.unread_notifications > 0 && (
            <Link to="/notifications" className={buttonClasses({ variant: "secondary" })}>
              🔔 {d.unread_notifications} unread notification{d.unread_notifications !== 1 ? "s" : ""}
            </Link>
          )}
          {d.bookmarked_count > 0 && (
            <Link to="/bookmarks" className={buttonClasses({ variant: "ghost" })}>
              🔖 {d.bookmarked_count} saved resource{d.bookmarked_count !== 1 ? "s" : ""}
            </Link>
          )}
        </div>
      </Card>

      {/* Quick links */}
      <Card className="space-y-3">
        <h2 className="text-lg font-bold">Quick links</h2>
        <div className="flex flex-wrap gap-2">
          <Link to="/resources" className={buttonClasses({ variant: "primary" })}>
            Find resources
          </Link>
          <Link to="/catalog" className={buttonClasses({ variant: "secondary" })}>
            Browse courses
          </Link>
          {can("order:create") && (
            <Link to="/print" className={buttonClasses({ variant: "secondary" })}>
              New print order
            </Link>
          )}
          <Link to="/bookmarks" className={buttonClasses({ variant: "ghost" })}>
            Bookmarks
          </Link>
          {can("resource:create") && (
            <Link to="/provider/resources" className={buttonClasses({ variant: "ghost" })}>
              My resources
            </Link>
          )}
        </div>
      </Card>

      {/* Recent print orders */}
      {d.recent_orders.length > 0 && (
        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-bold">Recent print orders</h2>
            <Link to="/print/orders" className="text-sm text-secondary hover:underline">
              View all
            </Link>
          </div>
          <ul className="divide-y divide-line">
            {d.recent_orders.map((order) => (
              <li key={order.id} className="py-3">
                <Link
                  to={`/print/orders/${order.id}`}
                  className="flex items-center justify-between gap-3 hover:opacity-80"
                >
                  <div>
                    <p className="font-semibold">{order.shop_name}</p>
                    <p className="text-sm text-fg-muted">
                      {formatUgx(order.total_ugx)} · {new Date(order.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <StatusBadge status={order.status} />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Recent resources (for providers) */}
      {d.recent_resources.length > 0 && (
        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-lg font-bold">My recent resources</h2>
            <Link to="/provider/resources" className="text-sm text-secondary hover:underline">
              Manage
            </Link>
          </div>
          <ul className="divide-y divide-line">
            {d.recent_resources.map((r) => (
              <li key={r.id} className="py-3">
                <Link
                  to={`/resources/${r.id}`}
                  className="flex items-center justify-between gap-3 hover:opacity-80"
                >
                  <div>
                    <p className="font-semibold">{r.title}</p>
                    <p className="text-sm text-fg-muted">{r.category_name}</p>
                  </div>
                  <span className="text-xs text-fg-muted">{r.access_type}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Empty state for new users */}
      {d.recent_orders.length === 0 && d.recent_resources.length === 0 && (
        <Card className="space-y-3">
          <h2 className="text-lg font-bold">Getting started</h2>
          <p className="text-fg-muted">
            Start by browsing academic resources from your university, or create a print order.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link to="/resources" className={buttonClasses({ variant: "primary" })}>
              Browse resources
            </Link>
            {can("order:create") && (
              <Link to="/print" className={buttonClasses({ variant: "secondary" })}>
                Print a document
              </Link>
            )}
          </div>
        </Card>
      )}
    </div>
  );
}
