import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SkeletonStatGrid, SkeletonList } from "@/components/ui/Skeleton";
import {
  Printer,
  Package,
  Clock,
  CheckCircle,
  ArrowRight,
  RefreshCw,
} from "@/components/ui/Icon";
import { useAuth } from "@/features/auth/auth-context";
import { getOperatorStats } from "@/features/dashboard/stats-api";
import { OrderStatusBadge, PaymentStatusBadge } from "@/features/printing/OrderBadges";
import { listQueue } from "@/features/operator/api";
import { toUserMessage } from "@/lib/api/errors";
import { formatUgx } from "@/lib/format";
import { cn } from "@/lib/cn";

function StatCard({
  label,
  value,
  to,
  colorClass = "text-fg",
  icon,
  description,
}: {
  label: string;
  value: number;
  to?: string;
  colorClass?: string;
  icon: React.ReactNode;
  description?: string;
}) {
  const inner = (
    <div className="p-4 space-y-2">
      <div className="flex items-center justify-between">
        <div className={cn("rounded-control bg-surface p-2", colorClass)}>{icon}</div>
        <p className={cn("text-3xl font-extrabold", colorClass)}>{value}</p>
      </div>
      <p className="font-semibold text-sm">{label}</p>
      {description && <p className="text-xs text-fg-muted">{description}</p>}
    </div>
  );

  return (
    <Card className="p-0 overflow-hidden">
      {to ? (
        <Link to={to} className="block hover:bg-surface/60 transition-colors">
          {inner}
        </Link>
      ) : (
        inner
      )}
    </Card>
  );
}

export function OperatorDashboard() {
  const { state } = useAuth();

  const statsQ = useQuery({
    queryKey:        ["dashboard", "operator-stats"],
    queryFn:         ({ signal }) => getOperatorStats(signal),
    enabled:         state.status === "authenticated",
    staleTime:       30_000,
    refetchInterval: 60_000,
  });

  const newOrdersQ = useQuery({
    queryKey:        ["operator", "queue", 1, "SUBMITTED", ""],
    queryFn:         ({ signal }) => listQueue({ page: 1, status: "SUBMITTED" }, signal),
    enabled:         state.status === "authenticated",
    staleTime:       15_000,
    refetchInterval: 30_000,
  });

  if (state.status !== "authenticated") return null;

  const firstName = state.me.user.full_name.split(" ")[0];
  const stats     = statsQ.data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card className="space-y-4 border-l-4 border-l-warning">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-warning">
              Printing Operator
            </p>
            <h1 className="text-2xl font-extrabold mt-1">
              Operator workspace, {firstName}
            </h1>
            <p className="mt-1 text-sm text-fg-muted">
              Manage print orders, track queue status, and process jobs for your shop.
            </p>
          </div>
          {stats && stats.submitted > 0 && (
            <span className="rounded-full bg-warning/10 border border-warning/20 px-3 py-1 text-sm font-bold text-warning">
              {stats.submitted} new order{stats.submitted !== 1 ? "s" : ""} waiting
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <Link to="/operator" className={buttonClasses({ variant: "primary" })}>
            <Printer size="sm" aria-hidden />
            Open print queue
          </Link>
          <Link to="/operator?status=SUBMITTED" className={buttonClasses({ variant: "secondary" })}>
            View new orders
          </Link>
        </div>
      </Card>

      {/* Queue stats */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-bold text-fg-muted uppercase tracking-widest text-xs">
            Queue overview
          </h2>
          <span className="text-xs text-fg-muted inline-flex items-center gap-1">
            <RefreshCw size="xs" aria-hidden />
            Refreshes every 60 s
          </span>
        </div>

        {statsQ.isPending && <SkeletonStatGrid cols={4} />}
        {statsQ.isError && (
          <Alert variant="error">{toUserMessage(statsQ.error)}</Alert>
        )}

        {stats && (
          <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
            <StatCard
              label="New orders"
              value={stats.submitted}
              to="/operator?status=SUBMITTED"
              colorClass={stats.submitted > 0 ? "text-secondary" : "text-fg"}
              icon={<Package size="sm" aria-hidden />}
              description="Waiting for acceptance"
            />
            <StatCard
              label="Accepted"
              value={stats.accepted}
              to="/operator?status=ACCEPTED"
              colorClass="text-primary"
              icon={<CheckCircle size="sm" aria-hidden />}
              description="Waiting to start printing"
            />
            <StatCard
              label="Printing"
              value={stats.printing}
              to="/operator?status=PRINTING"
              colorClass="text-warning"
              icon={<Printer size="sm" aria-hidden />}
              description="Currently being printed"
            />
            <StatCard
              label="Ready for pickup"
              value={stats.ready}
              to="/operator?status=READY_FOR_PICKUP"
              colorClass="text-accent"
              icon={<Package size="sm" aria-hidden />}
              description="Waiting for student collection"
            />
          </div>
        )}
      </section>

      {/* New orders requiring immediate action */}
      <Card className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-bold">New orders requiring action</h2>
          <Link
            to="/operator?status=SUBMITTED"
            className="text-sm text-secondary hover:underline inline-flex items-center gap-1"
          >
            View all
            <ArrowRight size="xs" aria-hidden />
          </Link>
        </div>

        {newOrdersQ.isPending && <SkeletonList n={3} />}
        {newOrdersQ.isError && (
          <Alert variant="error">{toUserMessage(newOrdersQ.error)}</Alert>
        )}
        {newOrdersQ.data?.items.length === 0 && (
          <div className="flex items-center gap-2 py-4 text-sm text-fg-muted">
            <CheckCircle size="sm" className="text-accent" aria-hidden />
            No new orders right now.
          </div>
        )}
        {newOrdersQ.data && newOrdersQ.data.items.length > 0 && (
          <ul className="divide-y divide-line" aria-label="New print orders">
            {newOrdersQ.data.items.slice(0, 5).map((order) => (
              <li key={order.id} className="py-3">
                <Link
                  to={`/operator/orders/${order.id}`}
                  className="flex items-center justify-between gap-3 group"
                >
                  <div className="min-w-0">
                    <p className="font-semibold group-hover:text-brand transition-colors">
                      {order.student_name ?? "Student"} ·{" "}
                      {order.item_count} document{order.item_count === 1 ? "" : "s"}
                    </p>
                    <p className="text-sm text-fg-muted">
                      {formatUgx(order.total_ugx)} ·{" "}
                      <span className="inline-flex items-center gap-1">
                        <Clock size="xs" aria-hidden />
                        {new Date(order.created_at).toLocaleString()}
                      </span>
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <OrderStatusBadge status={order.status} />
                    <PaymentStatusBadge
                      status={order.payment_status}
                      method={order.payment_method}
                    />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Quick links */}
      <Card className="space-y-3">
        <h2 className="font-bold">Quick access</h2>
        <div className="grid gap-2 sm:grid-cols-2">
          {[
            {
              to:    "/operator?status=SUBMITTED",
              icon:  <Package size="sm" aria-hidden />,
              title: "New orders",
              desc:  "Accept or reject incoming jobs",
              color: "hover:border-warning hover:bg-warning/5",
            },
            {
              to:    "/operator?status=ACCEPTED",
              icon:  <CheckCircle size="sm" aria-hidden />,
              title: "Accepted",
              desc:  "Start printing when ready",
              color: "hover:border-primary hover:bg-brand/5",
            },
            {
              to:    "/operator?status=PRINTING",
              icon:  <Printer size="sm" aria-hidden />,
              title: "Printing now",
              desc:  "Mark as ready when done",
              color: "hover:border-warning hover:bg-warning/5",
            },
            {
              to:    "/operator?status=READY_FOR_PICKUP",
              icon:  <Package size="sm" aria-hidden />,
              title: "Ready for pickup",
              desc:  "Complete when student collects",
              color: "hover:border-accent hover:bg-accent/5",
            },
          ].map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                "flex items-center gap-3 rounded-control border border-line p-3 transition-colors",
                item.color,
              )}
            >
              <span className="text-fg-muted">{item.icon}</span>
              <div>
                <p className="font-semibold text-sm">{item.title}</p>
                <p className="text-xs text-fg-muted">{item.desc}</p>
              </div>
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
