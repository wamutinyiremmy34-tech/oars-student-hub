import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SkeletonStatGrid, SkeletonCard } from "@/components/ui/Skeleton";
import {
  Users,
  Building,
  BookOpen,
  Printer,
  Megaphone,
  Shield,
  GraduationCap,
  BarChart,
  Eye,
  ArrowRight,
  Bell,
} from "@/components/ui/Icon";
import { useAuth } from "@/features/auth/auth-context";
import { getAnalytics } from "@/features/admin/api";
import { getDashboard } from "@/features/dashboard/api";
import { toUserMessage } from "@/lib/api/errors";
import { cn } from "@/lib/cn";

function StatCard({
  label,
  value,
  colorClass = "text-fg",
  icon,
  to,
}: {
  label: string;
  value: number | string;
  colorClass?: string;
  icon: React.ReactNode;
  to?: string;
}) {
  const inner = (
    <div className="p-4 space-y-2 text-center">
      <div className={cn("inline-flex rounded-full bg-surface p-2", colorClass)}>{icon}</div>
      <p className={cn("text-3xl font-extrabold", colorClass)}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
      <p className="text-xs text-fg-muted leading-snug">{label}</p>
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

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <SkeletonCard />
      <SkeletonStatGrid cols={4} />
      <SkeletonCard />
    </div>
  );
}

/** Admin section links — each links to /admin?tab=<name> so the AdminPage can open the right tab. */
const ADMIN_SECTIONS = [
  { tab: "users",        icon: <Users size="sm" aria-hidden />,         title: "User management",     desc: "View, suspend, and reinstate users" },
  { tab: "institutions", icon: <Building size="sm" aria-hidden />,      title: "Institutions",         desc: "Create and edit universities" },
  { tab: "academic",     icon: <GraduationCap size="sm" aria-hidden />, title: "Academic structure",   desc: "Faculties, programmes, courses" },
  { tab: "printing",     icon: <Printer size="sm" aria-hidden />,       title: "Printing management",  desc: "All orders and print shops" },
  { tab: "advertising",  icon: <Megaphone size="sm" aria-hidden />,     title: "Advertising",          desc: "Advertisers, campaigns, and ads" },
  { tab: "audit",        icon: <Shield size="sm" aria-hidden />,        title: "Audit log",            desc: "Security and access audit trail" },
] as const;

export function AdminDashboard() {
  const { state } = useAuth();

  const analyticsQ = useQuery({
    queryKey:  ["admin", "analytics"],
    queryFn:   ({ signal }) => getAnalytics(signal),
    enabled:   state.status === "authenticated",
    staleTime: 60_000,
  });

  const dashQ = useQuery({
    queryKey: ["dashboard"],
    queryFn:  ({ signal }) => getDashboard(signal),
    enabled:  state.status === "authenticated",
    retry:    false,
  });

  if (state.status !== "authenticated") return null;

  const firstName = state.me.user.full_name.split(" ")[0];

  if (analyticsQ.isPending) return <LoadingSkeleton />;
  if (analyticsQ.isError) {
    return (
      <div className="space-y-4">
        <Alert variant="error">{toUserMessage(analyticsQ.error)}</Alert>
        <Button variant="secondary" onClick={() => void analyticsQ.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  const a = analyticsQ.data;
  const d = dashQ.data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card className="space-y-4 border-l-4 border-l-danger">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-danger-strong">
              Platform Administrator
            </p>
            <h1 className="text-2xl font-extrabold mt-1">Admin dashboard, {firstName}</h1>
            <p className="mt-1 text-sm text-fg-muted">
              Monitor the platform, manage users, resources, printing, and advertising.
            </p>
          </div>
        </div>

        {d && d.unread_notifications > 0 && (
          <Link to="/notifications" className={buttonClasses({ variant: "outline", size: "sm" })}>
            <Bell size="xs" aria-hidden />
            {d.unread_notifications} unread notification
            {d.unread_notifications !== 1 ? "s" : ""}
          </Link>
        )}
      </Card>

      {/* Key metrics */}
      <section>
        <h2 className="text-xs font-bold text-fg-muted uppercase tracking-widest mb-3">
          Platform overview
        </h2>
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
          <StatCard
            label="Total users"
            value={a.total_users}
            colorClass="text-brand"
            icon={<Users size="sm" aria-hidden />}
            to="/admin?tab=users"
          />
          <StatCard
            label="Resources"
            value={a.total_resources}
            icon={<BookOpen size="sm" aria-hidden />}
            to="/admin?tab=moderation"
          />
          <StatCard
            label="Published resources"
            value={a.published_resources}
            colorClass="text-accent"
            icon={<BookOpen size="sm" aria-hidden />}
          />
          <StatCard
            label="Print orders"
            value={a.total_orders}
            icon={<Printer size="sm" aria-hidden />}
            to="/admin?tab=printing"
          />
          <StatCard
            label="Completed orders"
            value={a.completed_orders}
            colorClass="text-accent"
            icon={<Printer size="sm" aria-hidden />}
          />
          <StatCard
            label="Ad impressions"
            value={a.total_impressions}
            colorClass="text-secondary"
            icon={<Eye size="sm" aria-hidden />}
            to="/admin?tab=advertising"
          />
          <StatCard
            label="Ad clicks"
            value={a.total_clicks}
            colorClass="text-secondary"
            icon={<BarChart size="sm" aria-hidden />}
            to="/admin?tab=advertising"
          />
        </div>
      </section>

      {/* Primary actions */}
      <Card className="space-y-4">
        <h2 className="font-bold">Quick access</h2>
        <div className="flex flex-wrap gap-2">
          <Link to="/admin" className={buttonClasses({ variant: "primary" })}>
            Full admin panel
          </Link>
          <Link to="/moderation" className={buttonClasses({ variant: "secondary" })}>
            Resource moderation
          </Link>
          <Link to="/resources" className={buttonClasses({ variant: "ghost" })}>
            Browse resources
          </Link>
        </div>
      </Card>

      {/* Admin sections grid — each links to its specific tab */}
      <section>
        <h2 className="text-xs font-bold text-fg-muted uppercase tracking-widest mb-3">
          Administration tools
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ADMIN_SECTIONS.map((item) => (
            <Link
              key={item.tab}
              to={`/admin?tab=${item.tab}`}
              className={cn(
                "flex items-center gap-3 rounded-card border border-line p-4",
                "hover:border-primary hover:bg-brand/5 hover:shadow-soft",
                "transition-all duration-150",
              )}
            >
              <div className="rounded-control bg-surface p-2 shrink-0 text-fg-muted">
                {item.icon}
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-sm">{item.title}</p>
                <p className="text-xs text-fg-muted truncate">{item.desc}</p>
              </div>
              <ArrowRight size="xs" className="text-fg-muted ml-auto shrink-0" aria-hidden />
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
