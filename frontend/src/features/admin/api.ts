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

export function createCampaign(body: {
  advertiser_id: string;
  name: string;
  starts_at?: string | null;
  ends_at?: string | null;
}) {
  return apiFetch("/ads/campaigns", { method: "POST", body, schema: campaignSchema });
}

export function updateCampaign(
  id: string,
  body: { name?: string; starts_at?: string | null; ends_at?: string | null; is_active?: boolean }
) {
  return apiFetch(`/ads/campaigns/${id}`, { method: "PATCH", body, schema: campaignSchema });
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

// ─── Institution management ───────────────────────────────────────────────────

const institutionSchema = z.object({
  id: z.string(),
  name: z.string(),
  code: z.string(),
  slug: z.string(),
});
export type InstitutionRow = z.infer<typeof institutionSchema>;

export function listInstitutions(signal?: AbortSignal) {
  return apiFetch("/institutions", { schema: z.array(institutionSchema), auth: false, signal });
}

export function createInstitution(body: { name: string; code: string; slug: string }) {
  return apiFetch("/institutions", { method: "POST", body, schema: institutionSchema });
}

export function updateInstitution(id: string, body: Partial<{ name: string; code: string; slug: string }>) {
  return apiFetch(`/institutions/${id}`, { method: "PATCH", body, schema: institutionSchema });
}

// ─── Admin printing management ────────────────────────────────────────────────

import { apiFetchPage } from "@/lib/api/client";
import { orderSummarySchema as _opOrderSummary } from "@/features/printing/api";
export type AdminOrderRow = z.infer<typeof _opOrderSummary>;

export function listAllOrders(opts: { page?: number; status?: string; shop_id?: string }, signal?: AbortSignal) {
  const params = new URLSearchParams();
  params.set("page", String(opts.page ?? 1));
  params.set("page_size", "20");
  if (opts.status) params.set("status", opts.status);
  if (opts.shop_id) params.set("shop_id", opts.shop_id);
  return apiFetchPage(`/operator/orders?${params.toString()}`, {
    schema: z.array(_opOrderSummary),
    signal,
  });
}

// ─── Academic admin API ───────────────────────────────────────────────────────

const facultySchema = z.object({
  id: z.string(),
  institution_id: z.string(),
  name: z.string(),
  kind: z.string(),
  code: z.string().nullable(),
  is_active: z.boolean(),
});
export type Faculty = z.infer<typeof facultySchema>;

const programSchema = z.object({
  id: z.string(),
  institution_id: z.string(),
  faculty_id: z.string(),
  department_id: z.string().nullable(),
  name: z.string(),
  code: z.string().nullable(),
  level: z.string(),
  duration_years: z.number().nullable(),
  is_active: z.boolean(),
});
export type Program = z.infer<typeof programSchema>;

const courseSchema = z.object({
  id: z.string(),
  institution_id: z.string(),
  faculty_id: z.string(),
  department_id: z.string().nullable(),
  code: z.string(),
  title: z.string(),
  credit_units: z.number().nullable(),
  is_active: z.boolean(),
});
export type CourseRow = z.infer<typeof courseSchema>;

export function createFaculty(body: { institution_id: string; name: string; kind?: string; code?: string | null }) {
  return apiFetch("/faculties", { method: "POST", body, schema: facultySchema });
}

export function updateFaculty(id: string, body: { name?: string; kind?: string; code?: string | null; is_active?: boolean }) {
  return apiFetch(`/faculties/${id}`, { method: "PATCH", body, schema: facultySchema });
}

export function createProgram(body: {
  faculty_id: string;
  department_id?: string | null;
  name: string;
  code?: string | null;
  level?: string;
  duration_years?: number | null;
}) {
  return apiFetch("/programs", { method: "POST", body, schema: programSchema });
}

export function updateProgram(id: string, body: { name?: string; code?: string | null; level?: string; duration_years?: number | null; is_active?: boolean }) {
  return apiFetch(`/programs/${id}`, { method: "PATCH", body, schema: programSchema });
}

export function createCourse(body: {
  faculty_id: string;
  department_id?: string | null;
  code: string;
  title: string;
  credit_units?: number | null;
}) {
  return apiFetch("/courses", { method: "POST", body, schema: courseSchema });
}

export function updateCourse(id: string, body: { title?: string; credit_units?: number | null; is_active?: boolean }) {
  return apiFetch(`/courses/${id}`, { method: "PATCH", body, schema: courseSchema });
}

// ─── Print shop management (admin) ───────────────────────────────────────────

export { shopSchema, ruleSchema } from "@/features/printing/api";
export type { Shop, Rule } from "@/features/printing/api";

import { shopSchema as _shopSchema, ruleSchema as _ruleSchema } from "@/features/printing/api";

export function listShopsAdmin(institutionId: string, signal?: AbortSignal) {
  return apiFetch(`/print/shops?institution_id=${institutionId}&include_inactive=true`, {
    schema: z.array(_shopSchema),
    signal,
  });
}

export function createShop(body: {
  institution_id: string;
  name: string;
  location?: string | null;
  pay_on_pickup_enabled?: boolean;
}) {
  return apiFetch("/print/shops", { method: "POST", body, schema: _shopSchema });
}

export function updateShop(
  id: string,
  body: { name?: string; location?: string | null; is_active?: boolean; pay_on_pickup_enabled?: boolean }
) {
  return apiFetch(`/print/shops/${id}`, { method: "PATCH", body, schema: _shopSchema });
}

export function addShopStaff(shopId: string, userId: string) {
  return apiFetch(`/print/shops/${shopId}/staff`, {
    method: "POST",
    body: { user_id: userId },
    schema: z.object({ message: z.string() }),
  });
}

export function removeShopStaff(shopId: string, userId: string) {
  return apiFetch(`/print/shops/${shopId}/staff/${userId}`, {
    method: "DELETE",
    schema: z.object({ message: z.string() }),
  });
}

export function listPricingRules(shopId: string, signal?: AbortSignal) {
  return apiFetch(`/print/shops/${shopId}/pricing`, { schema: z.array(_ruleSchema), signal });
}

export function addPricingRule(
  shopId: string,
  body: {
    kind: "PER_PAGE" | "PER_COPY" | "PER_ORDER";
    paper_size?: string | null;
    color_mode?: "BW" | "COLOR" | null;
    duplex?: boolean | null;
    option_key?: string | null;
    amount_ugx: number;
  }
) {
  return apiFetch(`/print/shops/${shopId}/pricing-rules`, { method: "POST", body, schema: _ruleSchema });
}

export function updatePricingRule(shopId: string, ruleId: string, body: { amount_ugx?: number; is_active?: boolean }) {
  return apiFetch(`/print/shops/${shopId}/pricing-rules/${ruleId}`, { method: "PATCH", body, schema: _ruleSchema });
}

// ─── Notifications admin ──────────────────────────────────────────────────────

export function triggerOutboxProcess() {
  return apiFetch("/notifications/process-outbox", {
    method: "POST",
    schema: z.object({ message: z.string() }),
  });
}

// ─── Role management ─────────────────────────────────────────────────────────

const roleAssignmentSchema = z.object({
  role: z.string(),
  institution_id: z.string().nullable(),
});
export type RoleAssignment = z.infer<typeof roleAssignmentSchema>;

export function grantRole(userId: string, role: string, institutionId?: string) {
  return apiFetch(`/users/${userId}/roles`, {
    method: "POST",
    body: { role, institution_id: institutionId ?? null },
    schema: roleAssignmentSchema,
  });
}

export function revokeRole(userId: string, roleName: string, institutionId?: string) {
  const qs = institutionId ? `?institution_id=${institutionId}` : "";
  return apiFetch(`/users/${userId}/roles/${roleName}${qs}`, {
    method: "DELETE",
    schema: z.object({ message: z.string() }),
  });
}
