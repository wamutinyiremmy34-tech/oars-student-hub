import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SkeletonList } from "@/components/ui/Skeleton";
import { Pagination } from "@/components/ui/Pagination";
import { Bell, CheckCircle, ArrowRight } from "@/components/ui/Icon";
import { cn } from "@/lib/cn";
import { toUserMessage } from "@/lib/api/errors";
import { listNotifications, markAllRead, markRead, type Notification } from "@/features/notifications/api";

function kindStyles(kind: string) {
  switch (kind) {
    case "SUCCESS": return "border-l-accent";
    case "WARNING": return "border-l-warning";
    case "ERROR":   return "border-l-danger";
    default:        return "border-l-secondary";
  }
}

function kindDot(kind: string) {
  switch (kind) {
    case "SUCCESS": return "bg-accent";
    case "WARNING": return "bg-warning";
    case "ERROR":   return "bg-danger";
    default:        return "bg-secondary";
  }
}

function NotificationRow({ n }: { n: Notification }) {
  const qc = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => markRead([n.id]),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  return (
    <li
      className={cn(
        "flex items-start gap-4 border-b border-line py-4 pl-4 pr-3 border-l-4",
        kindStyles(n.kind),
        !n.is_read && "bg-secondary/[0.03]",
      )}
    >
      {/* Unread dot */}
      <div className="mt-1.5 shrink-0">
        {!n.is_read ? (
          <span
            className={cn("inline-block h-2 w-2 rounded-full", kindDot(n.kind))}
            aria-label="Unread"
          />
        ) : (
          <span className="inline-block h-2 w-2" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        {n.action_url ? (
          <Link
            to={n.action_url}
            className="block font-semibold hover:underline hover:text-brand transition-colors line-clamp-2"
          >
            {n.title}
            <ArrowRight size="xs" className="inline ml-1" aria-hidden />
          </Link>
        ) : (
          <p className="font-semibold line-clamp-2">{n.title}</p>
        )}
        {n.body && (
          <p className="mt-1 text-sm text-fg-muted line-clamp-3 leading-relaxed">{n.body}</p>
        )}
        <p className="mt-1.5 text-xs text-fg-muted">
          {new Date(n.created_at).toLocaleString()}
        </p>
      </div>

      {!n.is_read && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending}
          className="shrink-0 text-xs"
          aria-label="Mark notification as read"
        >
          <CheckCircle size="xs" aria-hidden />
          <span className="hidden sm:inline">Mark read</span>
        </Button>
      )}
    </li>
  );
}

export function NotificationsPage() {
  const [page, setPage] = useState(1);
  const qc              = useQueryClient();

  const query = useQuery({
    queryKey: ["notifications", "list", page],
    queryFn:  ({ signal }) => listNotifications({ page, pageSize: 20 }, signal),
  });

  const markAll = useMutation({
    mutationFn: () => markAllRead(),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unreadCount =
    query.data?.items.filter((n) => !n.is_read).length ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold">Notifications</h1>
          {unreadCount > 0 && (
            <p className="mt-1 text-sm text-fg-muted">
              {unreadCount} unread notification{unreadCount !== 1 ? "s" : ""}
            </p>
          )}
        </div>
        {unreadCount > 0 && (
          <Button
            variant="secondary"
            onClick={() => markAll.mutate()}
            disabled={markAll.isPending}
          >
            <CheckCircle size="sm" aria-hidden />
            Mark all read
          </Button>
        )}
      </div>

      {/* Loading */}
      {query.isPending && (
        <Card>
          <SkeletonList n={5} />
        </Card>
      )}

      {/* Error */}
      {query.isError && (
        <Alert variant="error">{toUserMessage(query.error)}</Alert>
      )}

      {/* Empty state */}
      {query.data?.items.length === 0 && (
        <div className="flex flex-col items-center gap-4 py-16 text-center">
          <div className="rounded-full bg-surface p-6">
            <Bell size="xl" className="text-fg-muted" aria-hidden />
          </div>
          <div className="space-y-1">
            <p className="font-semibold">No notifications yet</p>
            <p className="text-sm text-fg-muted max-w-sm">
              You'll be notified when your print orders update, resources are approved, and more.
            </p>
          </div>
        </div>
      )}

      {/* Notification list */}
      {query.data && query.data.items.length > 0 && (
        <Card className="p-0 overflow-hidden">
          <ul role="list" aria-label="Notifications">
            {query.data.items.map((n) => (
              <NotificationRow key={n.id} n={n} />
            ))}
          </ul>

          {query.data.meta.total > 20 && (
            <div className="border-t border-line px-4 py-3">
              <Pagination
                page={page}
                pageSize={20}
                total={query.data.meta.total}
                onChange={setPage}
              />
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
