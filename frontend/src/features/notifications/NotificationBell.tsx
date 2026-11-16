import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";
import { toUserMessage } from "@/lib/api/errors";
import { getUnreadCount, listNotifications, markAllRead, markRead, type Notification } from "@/features/notifications/api";

function kindStyles(kind: string) {
  switch (kind) {
    case "SUCCESS": return "border-l-accent";
    case "WARNING": return "border-l-warning";
    case "ERROR":   return "border-l-danger";
    default:        return "border-l-secondary";
  }
}

function NotificationItem({ n, onRead }: { n: Notification; onRead: (id: string) => void }) {
  return (
    <li
      className={cn(
        "border-b border-line px-4 py-3 text-sm border-l-4",
        kindStyles(n.kind),
        !n.is_read && "bg-secondary/5",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {n.action_url ? (
            <Link
              to={n.action_url}
              className="block font-semibold hover:underline"
              onClick={() => !n.is_read && onRead(n.id)}
            >
              {n.title}
            </Link>
          ) : (
            <p className="font-semibold">{n.title}</p>
          )}
          {n.body && <p className="mt-0.5 text-fg-muted">{n.body}</p>}
          <p className="mt-1 text-xs text-fg-muted">
            {new Date(n.created_at).toLocaleString()}
          </p>
        </div>
        {!n.is_read && (
          <button
            type="button"
            aria-label="Mark as read"
            onClick={() => onRead(n.id)}
            className="mt-0.5 h-2 w-2 flex-shrink-0 rounded-full bg-secondary"
          />
        )}
      </div>
    </li>
  );
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const qc = useQueryClient();

  const countQ = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: ({ signal }) => getUnreadCount(signal),
    refetchInterval: 60_000,
  });
  const listQ = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: ({ signal }) => listNotifications({ page: 1, pageSize: 10 }, signal),
    enabled: open,
  });
  const markAll = useMutation({
    mutationFn: () => markAllRead(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  function onRead(id: string) {
    markRead([id]).then(() => qc.invalidateQueries({ queryKey: ["notifications"] }));
  }

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node) &&
          buttonRef.current && !buttonRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", handleKey);
    document.addEventListener("mousedown", handleClick);
    return () => {
      document.removeEventListener("keydown", handleKey);
      document.removeEventListener("mousedown", handleClick);
    };
  }, [open]);

  const count = countQ.data?.count ?? 0;

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label={`Notifications${count > 0 ? `, ${count} unread` : ""}`}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
        className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-control text-fg-muted hover:bg-surface focus-visible:ring-2"
      >
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
          <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
        </svg>
        {count > 0 && (
          <span
            aria-hidden="true"
            className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger-strong px-1 text-xs font-bold text-white"
          >
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>

      {open && (
        <div
          ref={panelRef}
          role="region"
          aria-label="Notifications"
          className="absolute right-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-card border border-line bg-raised shadow-lifted"
        >
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 className="text-sm font-extrabold">Notifications</h2>
            {count > 0 && (
              <button
                type="button"
                onClick={() => markAll.mutate()}
                disabled={markAll.isPending}
                className="text-xs text-secondary hover:underline disabled:opacity-50"
              >
                Mark all read
              </button>
            )}
          </div>

          {listQ.isPending && (
            <p role="status" className="px-4 py-6 text-center text-sm text-fg-muted">Loading…</p>
          )}
          {listQ.isError && (
            <p className="px-4 py-4 text-sm text-danger">{toUserMessage(listQ.error)}</p>
          )}
          {listQ.data && listQ.data.items.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-fg-muted">You're all caught up!</p>
          )}
          {listQ.data && listQ.data.items.length > 0 && (
            <ul role="list" className="max-h-80 overflow-y-auto">
              {listQ.data.items.map((n) => (
                <NotificationItem key={n.id} n={n} onRead={onRead} />
              ))}
            </ul>
          )}

          <div className="border-t border-line px-4 py-2 text-center">
            <Link
              to="/notifications"
              className="text-xs text-secondary hover:underline"
              onClick={() => setOpen(false)}
            >
              View all notifications
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
