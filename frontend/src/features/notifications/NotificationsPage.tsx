import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Pagination } from "@/components/ui/Pagination";
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

function NotificationRow({ n }: { n: Notification }) {
  const qc = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => markRead([n.id]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  return (
    <li
      className={cn(
        "flex items-start gap-4 border-b border-line py-4 border-l-4 pl-4",
        kindStyles(n.kind),
        !n.is_read && "bg-secondary/5",
      )}
    >
      <div className="min-w-0 flex-1">
        {n.action_url ? (
          <Link to={n.action_url} className="block font-semibold hover:underline">
            {n.title}
          </Link>
        ) : (
          <p className="font-semibold">{n.title}</p>
        )}
        {n.body && <p className="mt-1 text-sm text-fg-muted">{n.body}</p>}
        <p className="mt-1 text-xs text-fg-muted">{new Date(n.created_at).toLocaleString()}</p>
      </div>
      {!n.is_read && (
        <Button
          variant="ghost"
          size="md"
          onClick={() => toggle.mutate()}
          disabled={toggle.isPending}
          className="flex-shrink-0 text-xs"
        >
          Mark read
        </Button>
      )}
    </li>
  );
}

export function NotificationsPage() {
  const [page, setPage] = useState(1);
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ["notifications", "list", page],
    queryFn: ({ signal }) => listNotifications({ page, pageSize: 20 }, signal),
  });

  const markAll = useMutation({
    mutationFn: () => markAllRead(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-extrabold">Notifications</h1>
        <Button
          variant="secondary"
          onClick={() => markAll.mutate()}
          disabled={markAll.isPending}
        >
          Mark all read
        </Button>
      </div>

      {query.isPending && <p role="status" className="text-fg-muted">Loading…</p>}
      {query.isError && <Alert variant="error">{toUserMessage(query.error)}</Alert>}

      {query.data && (
        <Card className="p-0 overflow-hidden">
          {query.data.items.length === 0 ? (
            <p className="px-4 py-8 text-center text-fg-muted">No notifications yet.</p>
          ) : (
            <>
              <ul role="list">
                {query.data.items.map((n) => (
                  <NotificationRow key={n.id} n={n} />
                ))}
              </ul>
              <div className="px-4 py-3">
                <Pagination
                  page={page}
                  pageSize={20}
                  total={query.data.meta.total}
                  onChange={setPage}
                />
              </div>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
