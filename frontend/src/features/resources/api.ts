import { z } from "zod";
import { apiFetch, apiFetchPage, resolveApiUrl } from "@/lib/api/client";

const categorySchema = z.object({
  id: z.string(),
  name: z.string(),
  slug: z.string(),
  description: z.string().nullable(),
});
export type Category = z.infer<typeof categorySchema>;

const courseRefSchema = z.object({ id: z.string(), code: z.string(), title: z.string() });
export type CourseRef = z.infer<typeof courseRefSchema>;

const versionSchema = z.object({
  id: z.string(),
  version_number: z.number(),
  filename: z.string(),
  mime_type: z.string(),
  size_bytes: z.number(),
  is_current: z.boolean(),
  changelog: z.string().nullable(),
  created_at: z.string(),
});
export type Version = z.infer<typeof versionSchema>;

export const summarySchema = z.object({
  id: z.string(),
  title: z.string(),
  excerpt: z.string(),
  access_type: z.enum(["FREE", "PREMIUM"]),
  price_ugx: z.number().nullable(),
  status: z.string(),
  institution_id: z.string(),
  institution_name: z.string(),
  category: categorySchema,
  tags: z.array(z.string()),
  courses: z.array(courseRefSchema),
  academic_year: z.number().nullable(),
  provider_name: z.string(),
  published_at: z.string().nullable(),
  file: versionSchema.nullable(),
  is_bookmarked: z.boolean(),
});
export type ResourceSummary = z.infer<typeof summarySchema>;

export const detailSchema = summarySchema.extend({
  description: z.string(),
  preview_text: z.string().nullable(),
  versions: z.array(versionSchema),
  viewer: z.object({
    is_owner: z.boolean(),
    can_download: z.boolean(),
    download_block_reason: z.string().nullable(),
    is_bookmarked: z.boolean(),
    can_review: z.boolean(),
    can_publish: z.boolean(),
    entitlement_status: z.string().nullable(),
  }),
  latest_review: z
    .object({ decision: z.string(), reason: z.string().nullable(), created_at: z.string() })
    .nullable(),
});
export type ResourceDetail = z.infer<typeof detailSchema>;

const downloadSchema = z.object({
  url: z.string(),
  expires_in: z.number(),
  filename: z.string(),
  delivery: z.enum(["SIGNED_URL", "STREAM"]),
});
const messageSchema = z.object({ message: z.string() });

export interface SearchQuery {
  q?: string;
  institution_id?: string;
  faculty_id?: string;
  department_id?: string;
  program_id?: string;
  course_id?: string;
  category?: string;
  tag?: string;
  access?: "FREE" | "PREMIUM";
  academic_year?: number;
  sort?: "relevance" | "newest" | "title";
  page?: number;
  page_size?: number;
}

export function toQueryString(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function searchResources(query: SearchQuery, signal?: AbortSignal) {
  return apiFetchPage(`/search${toQueryString({ ...query })}`, {
    schema: z.array(summarySchema),
    signal,
  });
}

export function getResource(id: string, signal?: AbortSignal) {
  return apiFetch(`/resources/${id}`, { schema: detailSchema, signal });
}

export function listCategories(signal?: AbortSignal) {
  return apiFetch("/categories", { schema: z.array(categorySchema), auth: false, signal });
}

export function listBookmarks(page: number, signal?: AbortSignal) {
  return apiFetchPage(`/bookmarks${toQueryString({ page, page_size: 12 })}`, {
    schema: z.array(summarySchema),
    signal,
  });
}

export function setBookmark(id: string, on: boolean) {
  return apiFetch(`/bookmarks/${id}`, { method: on ? "PUT" : "DELETE", schema: messageSchema });
}

export async function requestDownload(id: string) {
  const link = await apiFetch(`/resources/${id}/download`, { method: "POST", schema: downloadSchema });
  return { ...link, url: resolveApiUrl(link.url) };
}

export function listMine(page: number, status?: string, signal?: AbortSignal) {
  return apiFetchPage(`/resources/mine${toQueryString({ page, page_size: 12, status })}`, {
    schema: z.array(summarySchema),
    signal,
  });
}

export function listReviewQueue(page: number, status?: string, signal?: AbortSignal) {
  return apiFetchPage(`/resources/review-queue${toQueryString({ page, page_size: 12, status })}`, {
    schema: z.array(summarySchema),
    signal,
  });
}

export interface ResourceInput {
  institution_id: string;
  category_id: string;
  title: string;
  description: string;
  preview_text?: string;
  access_type: "FREE" | "PREMIUM";
  price_ugx?: number;
  academic_year?: number;
  tags: string[];
  course_ids: string[];
}

export function createResource(input: ResourceInput) {
  return apiFetch("/resources", { method: "POST", body: input, schema: detailSchema });
}

export function updateResource(id: string, input: Partial<Omit<ResourceInput, "institution_id">>) {
  return apiFetch(`/resources/${id}`, { method: "PATCH", body: input, schema: detailSchema });
}

export function uploadVersion(id: string, file: File, changelog?: string) {
  const form = new FormData();
  form.append("file", file);
  if (changelog) form.append("changelog", changelog);
  return apiFetch(`/resources/${id}/versions`, { method: "POST", body: form, schema: versionSchema, timeoutMs: 120_000 });
}

export type LifecycleAction = "submit" | "start-review" | "approve" | "reject" | "publish" | "archive";

export function runLifecycle(id: string, action: LifecycleAction, body?: { reason?: string; note?: string }) {
  return apiFetch(`/resources/${id}/${action}`, { method: "POST", body: body ?? {}, schema: detailSchema });
}

export function deleteDraft(id: string) {
  return apiFetch(`/resources/${id}`, { method: "DELETE", schema: messageSchema });
}
