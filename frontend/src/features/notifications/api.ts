import { z } from "zod";
import { apiFetch, apiFetchPage } from "@/lib/api/client";

export const notificationSchema = z.object({
  id: z.string(),
  kind: z.enum(["INFO", "SUCCESS", "WARNING", "ERROR"]),
  title: z.string(),
  body: z.string().nullable(),
  action_url: z.string().nullable(),
  is_read: z.boolean(),
  read_at: z.string().nullable(),
  created_at: z.string(),
});
export type Notification = z.infer<typeof notificationSchema>;

const unreadCountSchema = z.object({ count: z.number() });
const messageSchema = z.object({ message: z.string() });

export function listNotifications(opts: { unreadOnly?: boolean; page?: number; pageSize?: number }, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (opts.unreadOnly) params.set("unread_only", "true");
  if (opts.page) params.set("page", String(opts.page));
  if (opts.pageSize) params.set("page_size", String(opts.pageSize));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiFetchPage(`/notifications${qs}`, { schema: z.array(notificationSchema), signal });
}

export function getUnreadCount(signal?: AbortSignal) {
  return apiFetch("/notifications/unread-count", { schema: unreadCountSchema, signal });
}

export function markRead(ids: string[]) {
  return apiFetch("/notifications/mark-read", {
    method: "POST",
    body: { ids },
    schema: messageSchema,
  });
}

export function markAllRead() {
  return apiFetch("/notifications/mark-read", {
    method: "POST",
    body: { ids: [] },
    schema: messageSchema,
  });
}
