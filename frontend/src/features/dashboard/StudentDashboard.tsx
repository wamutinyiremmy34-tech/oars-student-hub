import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SkeletonCard, SkeletonStatGrid } from "@/components/ui/Skeleton";
import {
  BookOpen,
  GraduationCap,
  Printer,
  Bookmark,
  Bell,
  ArrowRight,
  Clock,
  CheckCircle,
} from "@/components/ui/Icon";
import { useAuth } from "@/features/auth/auth-context";
import { getDashboard } from "@/features/dashboard/api";
import { AdBanner } from "@/features/admin/AdBanner";
import { formatUgx } from "@/lib/format";
import { toUserMessage } from "@/lib/api/errors";
import { cn } from "@/lib/cn";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    SUBMITTED:        "Submitted",
    ACCEPTED:         "Accepted",
    PRINTING:         "Printing",
    READY_FOR_PICKUP: "Ready for pickup",
    COMPLETED:        "Completed",
    CANCELLED:        "Cancelled",
    REJECTED:         "Rejected",
  };
  const colors: Record<string, string> = {
    READY_FOR_PICKUP: "bg-accent/10 text-accent",
    COMPLETED:        "bg-accent/10 text-accent",
    REJECTED:         "bg-danger/10 text-danger-strong",
    CANCELLED:        "bg-warning/10 text-warning",
  };
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-semibold",
        colors[status] ?? "bg-secondary/10 text-secondary",
      )}
    >
      {labels[status] ?? status}
    </span>
  );
}

function QuickActionCard({
  to,
  icon,
  title,
  description,
}: {
  to: string;
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <Link
      to={to}
      className={cn(
        "flex flex-col items-center gap-2 rounded-card border border-line p-4 text-center",
        "hover:border-brand hover:bg-brand/5 hover:shadow-soft",
        "transition-all duration-150",
      )}
    >
      <div className="rounded-full bg-brand/10 p-3 text-brand">{icon}</div>
      <span className="font-semibold text-sm">{title}</span>
      <span className="text-xs text-fg-muted leading-relaxed">{description}</span>
    </Link>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <SkeletonCard />
      <SkeletonStatGrid cols={4} />
      <SkeletonCard />
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function StudentDashboard() {
  const { state } = useAuth();
  const dashQ = useQuery({
    queryKey: ["dashboard"],
    queryFn: ({ signal }) => getDashboard(signal),
    enabled: state.status === "authenticated",
    retry: false,
  });

  if (state.status !== "authenticated") return null;

  const institutionId = state.me.student_profile?.institution_id;
  const firstName = state.me.user.full_name.split(" ")[0];

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
      {/* Welcome header */}
      <Card className="space-y-4 border-l-4 border-l-brand">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-brand">
              Student
            </p>
            <h1 className="text-2xl font-extrabold mt-1 leading-tight">
              Welcome back, {firstName}!
            </h1>
            <p className="mt-1 text-sm text-fg-muted">{d.greeting}</p>
          </div>
          {!state.me.user.email_verified && (
            <span className="rounded-full bg-warning/10 border border-warning/20 px-3 py-1 text-xs font-semibold text-warning">
              Email not verified
            </span>
          )}
        </div>

        {/* Notification + bookmark shortcuts */}
        <div className="flex flex-wrap gap-2">
          {d.unread_notifications > 0 && (
            <Link
              to="/notifications"
              className={buttonClasses({ variant: "outline", size: "sm" })}
            >
              <Bell size="xs" aria-hidden />
              {d.unread_notifications} unread notification
              {d.unread_notifications !== 1 ? "s" : ""}
            </Link>
          )}
          {d.bookmarked_count > 0 && (
            <Link to="/bookmarks" className={buttonClasses({ variant: "secondary", size: "sm" })}>
              <Bookmark size="xs" aria-hidden />
              {d.bookmarked_count} saved resource
              {d.bookmarked_count !== 1 ? "s" : ""}
            </Link>
          )}
        </div>
      </Card>

      {/* Quick actions */}
      <section>
        <h2 className="text-base font-bold mb-3 text-fg-muted uppercase tracking-widest text-xs">
          Quick actions
        </h2>
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
          <QuickActionCard
            to="/resources"
            icon={<BookOpen size="md" />}
            title="Find resources"
            description="Notes, past papers and more"
          />
          <QuickActionCard
            to="/catalog"
            icon={<GraduationCap size="md" />}
            title="Browse courses"
            description="By faculty and programme"
          />
          <QuickActionCard
            to="/print"
            icon={<Printer size="md" />}
            title="Print a document"
            description="Upload and order printing"
          />
          <QuickActionCard
            to="/bookmarks"
            icon={<Bookmark size="md" />}
            title="Saved items"
            description={`${d.bookmarked_count} bookmarked resource${d.bookmarked_count !== 1 ? "s" : ""}`}
          />
        </div>
      </section>

      {/* Recent print orders */}
      {d.recent_orders.length > 0 ? (
        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-base font-bold flex items-center gap-2">
              <Printer size="sm" className="text-fg-muted" aria-hidden />
              My print orders
            </h2>
            <Link
              to="/print/orders"
              className="text-sm text-secondary hover:underline inline-flex items-center gap-1"
            >
              View all
              <ArrowRight size="xs" aria-hidden />
            </Link>
          </div>
          <ul className="divide-y divide-line" aria-label="Recent print orders">
            {d.recent_orders.map((order) => (
              <li key={order.id} className="py-3">
                <Link
                  to={`/print/orders/${order.id}`}
                  className="flex items-center justify-between gap-3 group"
                >
                  <div className="min-w-0">
                    <p className="font-semibold truncate group-hover:text-brand transition-colors">
                      {order.shop_name}
                    </p>
                    <p className="text-sm text-fg-muted">
                      {formatUgx(order.total_ugx)} ·{" "}
                      {new Date(order.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <StatusBadge status={order.status} />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <Card className="space-y-3">
          <h2 className="text-base font-bold flex items-center gap-2">
            <Printer size="sm" className="text-fg-muted" aria-hidden />
            Print orders
          </h2>
          <p className="text-sm text-fg-muted">
            You haven't placed any print orders yet.
          </p>
          <Link to="/print" className={buttonClasses({ variant: "primary", size: "sm" })}>
            Place your first order
          </Link>
        </Card>
      )}

      {/* Ad banner */}
      {institutionId && (
        <AdBanner placement="dashboard_banner" institutionId={institutionId} />
      )}

      {/* Getting started card — only for new users */}
      {d.recent_orders.length === 0 && d.bookmarked_count === 0 && (
        <Card className="space-y-4 bg-brand/5 border-brand/20" variant="outlined">
          <h2 className="text-base font-bold">New to OARS?</h2>
          <div className="grid gap-2 sm:grid-cols-3 text-sm text-fg-muted">
            <div className="flex items-start gap-2">
              <CheckCircle size="sm" className="text-accent mt-0.5 shrink-0" aria-hidden />
              <span>Find lecture notes, past papers and study resources for your courses.</span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircle size="sm" className="text-accent mt-0.5 shrink-0" aria-hidden />
              <span>Upload documents and get them printed at a campus shop near you.</span>
            </div>
            <div className="flex items-start gap-2">
              <CheckCircle size="sm" className="text-accent mt-0.5 shrink-0" aria-hidden />
              <span>Track your printing orders and get notified when they're ready.</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to="/resources" className={buttonClasses({ variant: "primary" })}>
              Browse resources
            </Link>
            <Link to="/catalog" className={buttonClasses({ variant: "secondary" })}>
              Browse by course
            </Link>
          </div>
        </Card>
      )}

      {/* Recent resources from dashboard */}
      {d.recent_resources && d.recent_resources.length > 0 && (
        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-base font-bold flex items-center gap-2">
              <BookOpen size="sm" className="text-fg-muted" aria-hidden />
              Recent resources
            </h2>
            <Link
              to="/resources"
              className="text-sm text-secondary hover:underline inline-flex items-center gap-1"
            >
              Browse all
              <ArrowRight size="xs" aria-hidden />
            </Link>
          </div>
          <ul className="divide-y divide-line" aria-label="Recent resources">
            {d.recent_resources.map((r) => (
              <li key={r.id} className="py-3">
                <Link
                  to={`/resources/${r.id}`}
                  className="flex items-center justify-between gap-3 group"
                >
                  <div className="min-w-0">
                    <p className="font-semibold truncate group-hover:text-brand transition-colors">
                      {r.title}
                    </p>
                    <p className="text-xs text-fg-muted">
                      {r.category_name} · {r.institution_name}
                    </p>
                  </div>
                  <span className="text-xs text-fg-muted capitalize shrink-0">
                    {r.access_type.toLowerCase()}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Study tip */}
      <Card variant="flat" className="flex items-start gap-3 p-3">
        <Clock size="sm" className="text-fg-muted mt-0.5 shrink-0" aria-hidden />
        <p className="text-xs text-fg-muted leading-relaxed">
          <strong>Tip:</strong> Save resources to your bookmarks for quick access during exams and
          revision. Find them anytime under <strong>Saved</strong> in the navigation.
        </p>
      </Card>
    </div>
  );
}
