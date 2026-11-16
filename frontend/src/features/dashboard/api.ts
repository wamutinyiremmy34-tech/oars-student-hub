import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

const recentResourceSchema = z.object({
  id: z.string(),
  title: z.string(),
  access_type: z.string(),
  category_name: z.string(),
  institution_name: z.string(),
});

const recentOrderSchema = z.object({
  id: z.string(),
  status: z.string(),
  payment_status: z.string(),
  shop_name: z.string(),
  total_ugx: z.number(),
  created_at: z.string(),
});

const dashboardSchema = z.object({
  greeting: z.string(),
  unread_notifications: z.number(),
  recent_resources: z.array(recentResourceSchema),
  recent_orders: z.array(recentOrderSchema),
  bookmarked_count: z.number(),
});
export type Dashboard = z.infer<typeof dashboardSchema>;

export function getDashboard(signal?: AbortSignal) {
  return apiFetch("/dashboard", { schema: dashboardSchema, signal });
}
