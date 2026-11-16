import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

// ─── Dashboard analytics ───────────────────────────────────────────────────

const analyticsSchema = z.object({
  total_users: z.number(),
  total_resources: z.number(),
  published_resources: z.number(),
  total_orders: z.number(),
  completed_orders: z.number(),
  total_impressions: z.number(),
  total_clicks: z.number(),
});
export type Analytics = z.infer<typeof analyticsSchema>;

export function getAnalytics(signal?: AbortSignal) {
  return apiFetch("/analytics", { schema: analyticsSchema, signal });
}

// ─── User management ──────────────────────────────────────────────────────

const adminUserRowSchema = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string(),
  status: z.string(),
  email_verified: z.boolean(),
  created_at: z.string(),
  roles: z.array(z.string()),
});
export type AdminUserRow = z.infer<typeof adminUserRowSchema>;

const adminUserListSchema = z.object({
  items: z.array(adminUserRowSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
});

export function listAdminUsers(opts: { page?: number; q?: string; status?: string }, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (opts.page) params.set("page", String(opts.page));
  if (opts.q) params.set("q", opts.q);
  if (opts.status) params.set("status", opts.status);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiFetch(`/admin/users${qs}`, { schema: adminUserListSchema, signal });
}

export function suspendUser(userId: string, reason: string) {
  return apiFetch(`/users/${userId}/suspend`, {
    method: "POST",
    body: { reason },
    schema: z.object({ user: z.object({ id: z.string(), status: z.string(), full_name: z.string() }) }),
  });
}

export function reinstateUser(userId: string) {
  return apiFetch(`/users/${userId}/reinstate`, {
    method: "POST",
    body: {},
    schema: z.object({ user: z.object({ id: z.string(), status: z.string(), full_name: z.string() }) }),
  });
}

// ─── Audit logs ───────────────────────────────────────────────────────────

const auditLogSchema = z.object({
  id: z.string(),
  actor_user_id: z.string().nullable(),
  action: z.string(),
  outcome: z.string(),
  target_type: z.string().nullable(),
  target_id: z.string().nullable(),
  institution_id: z.string().nullable(),
  ip_address: z.string().nullable(),
  created_at: z.string(),
});
export type AuditLog = z.infer<typeof auditLogSchema>;

const auditLogListSchema = z.object({
  items: z.array(auditLogSchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
});

export function listAuditLogs(opts: { page?: number; action?: string }, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (opts.page) params.set("page", String(opts.page));
  if (opts.action) params.set("action", opts.action);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiFetch(`/admin/audit-logs${qs}`, { schema: auditLogListSchema, signal });
}

// ─── Advertising (admin) ──────────────────────────────────────────────────

const advertiserSchema = z.object({
  id: z.string(),
  name: z.string(),
  contact_email: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
});
export type Advertiser = z.infer<typeof advertiserSchema>;

const campaignSchema = z.object({
  id: z.string(),
  advertiser_id: z.string(),
  name: z.string(),
  starts_at: z.string().nullable(),
  ends_at: z.string().nullable(),
  is_active: z.boolean(),
  created_at: z.string(),
});
export type Campaign = z.infer<typeof campaignSchema>;

const adSchema = z.object({
  id: z.string(),
  campaign_id: z.string(),
  status: z.string(),
  title: z.string(),
  body: z.string().nullable(),
  image_url: z.string().nullable(),
  click_url: z.string().nullable(),
  placement: z.string(),
  starts_at: z.string().nullable(),
  ends_at: z.string().nullable(),
  rejection_reason: z.string().nullable(),
  target_institution_ids: z.array(z.string().nullable()),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Ad = z.infer<typeof adSchema>;

const adMetricsSchema = z.object({
  advertisement_id: z.string(),
  impressions: z.number(),
  clicks: z.number(),
});
export type AdMetrics = z.infer<typeof adMetricsSchema>;

export function listAdvertisers(signal?: AbortSignal) {
  return apiFetch("/ads/advertisers", { schema: z.array(advertiserSchema), signal });
}

export function createAdvertiser(body: { name: string; contact_email: string }) {
  return apiFetch("/ads/advertisers", { method: "POST", body, schema: advertiserSchema });
}

export function listCampaigns(advertiserId?: string, signal?: AbortSignal) {
  const qs = advertiserId ? `?advertiser_id=${advertiserId}` : "";
  return apiFetch(`/ads/campaigns${qs}`, { schema: z.array(campaignSchema), signal });
}

export function listAds(opts: { campaignId?: string; status?: string }, signal?: AbortSignal) {
  const params = new URLSearchParams();
  if (opts.campaignId) params.set("campaign_id", opts.campaignId);
  if (opts.status) params.set("status", opts.status);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return apiFetch(`/ads/advertisements${qs}`, { schema: z.array(adSchema), signal });
}

export function createAd(body: {
  campaign_id: string;
  title: string;
  body?: string | null;
  image_url?: string | null;
  click_url?: string | null;
  placement: string;
  starts_at?: string | null;
  ends_at?: string | null;
  target_institution_ids: string[];
}) {
  return apiFetch("/ads/advertisements", { method: "POST", body, schema: adSchema });
}

export function changeAdStatus(adId: string, status: string, rejection_reason?: string) {
  return apiFetch(`/ads/advertisements/${adId}/status`, {
    method: "POST",
    body: { status, rejection_reason },
    schema: adSchema,
  });
}

export function getAdMetrics(adId: string, signal?: AbortSignal) {
  return apiFetch(`/ads/advertisements/${adId}/metrics`, { schema: adMetricsSchema, signal });
}
