import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SkeletonCard, SkeletonStatGrid } from "@/components/ui/Skeleton";
import {
  Upload,
  FileText,
  CheckCircle,
  XCircle,
  Clock,
  ArrowRight,
  BookOpen,
  Bell,
} from "@/components/ui/Icon";
import { useAuth } from "@/features/auth/auth-context";
import { getDashboard } from "@/features/dashboard/api";
import { getProviderStats } from "@/features/dashboard/stats-api";
import { toUserMessage } from "@/lib/api/errors";
import { cn } from "@/lib/cn";

function StatCard({
  label,
  value,
  to,
  colorClass = "text-fg",
  icon,
}: {
  label: string;
  value: number | string;
  to?: string;
  colorClass?: string;
  icon: React.ReactNode;
}) {
  const inner = (
    <div className="flex flex-col items-center gap-2 py-4 px-3">
      <div className={cn("rounded-full bg-surface p-2", colorClass)}>{icon}</div>
      <p className={cn("text-3xl font-extrabold", colorClass)}>{value}</p>
      <p className="text-xs text-fg-muted text-center leading-snug">{label}</p>
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

export function ProviderDashboard() {
  const { state } = useAuth();

  const dashQ = useQuery({
    queryKey: ["dashboard"],
    queryFn:  ({ signal }) => getDashboard(signal),
    enabled:  state.status === "authenticated",
    retry:    false,
  });

  const statsQ = useQuery({
    queryKey:  ["dashboard", "provider-stats"],
    queryFn:   ({ signal }) => getProviderStats(signal),
    enabled:   state.status === "authenticated",
    staleTime: 60_000,
  });

  if (state.status !== "authenticated") return null;

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

  const d     = dashQ.data;
  const stats = statsQ.data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card className="space-y-4 border-l-4 border-l-secondary">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-secondary">
              Resource Provider
            </p>
            <h1 className="text-2xl font-extrabold mt-1">
              Provider workspace, {firstName}
            </h1>
            <p className="mt-1 text-sm text-fg-muted">
              Manage your academic resources and track their review status.
            </p>
          </div>
          {!state.me.user.email_verified && (
            <span className="rounded-full bg-warning/10 border border-warning/20 px-3 py-1 text-xs font-semibold text-warning">
              Email not verified
            </span>
          )}
        </div>

        {d.unread_notifications > 0 && (
          <Link to="/notifications" className={buttonClasses({ variant: "outline", size: "sm" })}>
            <Bell size="xs" aria-hidden />
            {d.unread_notifications} unread notification
            {d.unread_notifications !== 1 ? "s" : ""}
          </Link>
        )}
      </Card>

      {/* Resource stats */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-bold text-fg-muted uppercase tracking-widest text-xs">
            My resources
          </h2>
          <Link
            to="/provider/resources"
            className="text-sm text-secondary hover:underline inline-flex items-center gap-1"
          >
            View all
            <ArrowRight size="xs" aria-hidden />
          </Link>
        </div>

        {statsQ.isPending && <SkeletonStatGrid cols={4} />}

        {stats && (
          <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
            <StatCard
              label="Total"
              value={stats.total}
              to="/provider/resources"
              icon={<BookOpen size="sm" aria-hidden />}
            />
            <StatCard
              label="Published"
              value={stats.published}
              to="/provider/resources?status=PUBLISHED"
              colorClass="text-accent"
              icon={<CheckCircle size="sm" aria-hidden />}
            />
            <StatCard
              label="Pending review"
              value={stats.pending}
              to="/provider/resources?status=SUBMITTED"
              colorClass="text-secondary"
              icon={<Clock size="sm" aria-hidden />}
            />
            <StatCard
              label="Rejected"
              value={stats.rejected}
              to="/provider/resources?status=REJECTED"
              colorClass="text-danger-strong"
              icon={<XCircle size="sm" aria-hidden />}
            />
          </div>
        )}
      </section>

      {/* Primary actions */}
      <Card className="space-y-4">
        <h2 className="font-bold">Actions</h2>
        <div className="flex flex-wrap gap-3">
          <Link to="/provider/resources/new" className={buttonClasses({ variant: "primary" })}>
            <Upload size="sm" aria-hidden />
            Upload a new resource
          </Link>
          <Link to="/provider/resources" className={buttonClasses({ variant: "secondary" })}>
            <FileText size="sm" aria-hidden />
            Manage my resources
          </Link>
          {stats && stats.rejected > 0 && (
            <Link
              to="/provider/resources?status=REJECTED"
              className={buttonClasses({ variant: "outline" })}
            >
              <XCircle size="sm" aria-hidden />
              Review {stats.rejected} rejected
            </Link>
          )}
        </div>
      </Card>

      {/* Recent submissions */}
      {d.recent_resources.length > 0 ? (
        <Card className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-bold">Recent submissions</h2>
            <Link
              to="/provider/resources"
              className="text-sm text-secondary hover:underline inline-flex items-center gap-1"
            >
              Manage all
              <ArrowRight size="xs" aria-hidden />
            </Link>
          </div>
          <ul className="divide-y divide-line" aria-label="Recent resource submissions">
            {d.recent_resources.map((r) => (
              <li key={r.id} className="py-3">
                <Link
                  to={`/provider/resources/${r.id}`}
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
      ) : (
        <Card className="space-y-3 bg-secondary/5 border-secondary/20" variant="outlined">
          <h2 className="font-bold">No resources yet</h2>
          <p className="text-sm text-fg-muted">
            Upload your first academic resource and submit it for review. Once approved, students
            at your institution can access it.
          </p>
          <Link to="/provider/resources/new" className={buttonClasses({ variant: "primary" })}>
            <Upload size="sm" aria-hidden />
            Upload first resource
          </Link>
        </Card>
      )}

      {/* How moderation works */}
      <Card className="space-y-3" variant="flat">
        <h2 className="font-bold">How publishing works</h2>
        <ol className="space-y-2 text-sm text-fg-muted list-none">
          {[
            "Upload a file and fill in the resource details.",
            'Click "Submit for review" — your resource enters the review queue.',
            "A reviewer checks it for quality and policy compliance.",
            "Once approved, it is published and visible to students.",
            "If rejected, you'll receive feedback and can edit and resubmit.",
          ].map((step, i) => (
            <li key={i} className="flex items-start gap-3">
              <span className="shrink-0 inline-flex h-5 w-5 items-center justify-center rounded-full bg-secondary/10 text-secondary text-xs font-bold">
                {i + 1}
              </span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
