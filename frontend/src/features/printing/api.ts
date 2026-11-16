import { z } from "zod";
import { apiFetch, apiFetchPage } from "@/lib/api/client";
import { toQueryString } from "@/features/resources/api";

export const shopSchema = z.object({
  id: z.string(),
  institution_id: z.string(),
  name: z.string(),
  location: z.string().nullable(),
  is_active: z.boolean(),
  pay_on_pickup_enabled: z.boolean(),
});
export type Shop = z.infer<typeof shopSchema>;

export const ruleSchema = z.object({
  id: z.string(),
  kind: z.enum(["PER_PAGE", "PER_COPY", "PER_ORDER"]),
  paper_size: z.string().nullable(),
  color_mode: z.enum(["BW", "COLOR"]).nullable(),
  duplex: z.boolean().nullable(),
  option_key: z.string().nullable(),
  amount_ugx: z.number(),
  is_active: z.boolean(),
});
export type Rule = z.infer<typeof ruleSchema>;

export const documentSchema = z.object({ id: z.string(), filename: z.string(), page_count: z.number(), size_bytes: z.number() });
export type PrintDocument = z.infer<typeof documentSchema>;

const quoteSchema = z.object({
  shop_id: z.string(),
  currency: z.string(),
  total_ugx: z.number(),
  items: z.array(
    z.object({
      document_id: z.string(),
      filename: z.string(),
      page_count: z.number(),
      copies: z.number(),
      paper_size: z.string(),
      color_mode: z.string(),
      duplex: z.boolean(),
      options: z.record(z.string(), z.boolean()),
      unit_price_ugx: z.number(),
      line_total_ugx: z.number(),
    }),
  ),
  order_lines: z.array(z.object({ label: z.string(), amount_ugx: z.number() })),
});
export type Quote = z.infer<typeof quoteSchema>;

const paymentSummarySchema = z.object({
  id: z.string(),
  status: z.string(),
  method: z.string(),
  amount_ugx: z.number(),
  checkout_url: z.string().nullable(),
  created_at: z.string(),
  paid_at: z.string().nullable(),
});

export const orderSchema = z.object({
  id: z.string(),
  status: z.string(),
  payment_method: z.enum(["ONLINE", "PAY_ON_PICKUP"]),
  payment_status: z.string(),
  total_ugx: z.number(),
  currency: z.string(),
  shop: shopSchema,
  items: z.array(
    z.object({
      id: z.string(),
      position: z.number(),
      filename: z.string(),
      page_count: z.number(),
      copies: z.number(),
      paper_size: z.string(),
      color_mode: z.string(),
      duplex: z.boolean(),
      options: z.record(z.string(), z.unknown()),
      unit_price_ugx: z.number(),
      line_total_ugx: z.number(),
      document_available: z.boolean(),
    }),
  ),
  history: z.array(z.object({ from_status: z.string().nullable(), to_status: z.string(), note: z.string().nullable(), created_at: z.string() })),
  payment: paymentSummarySchema.nullable(),
  note: z.string().nullable(),
  reject_reason: z.string().nullable(),
  cancel_reason: z.string().nullable(),
  pickup_code: z.string().nullable(),
  can_cancel: z.boolean(),
  awaiting_payment: z.boolean(),
  created_at: z.string(),
  student_name: z.string().nullable().optional(),
  retention_hold: z.boolean().nullable().optional(),
});
export type Order = z.infer<typeof orderSchema>;

export const orderSummarySchema = z.object({
  id: z.string(),
  status: z.string(),
  payment_method: z.string(),
  payment_status: z.string(),
  total_ugx: z.number(),
  shop_name: z.string(),
  item_count: z.number(),
  created_at: z.string(),
  student_name: z.string().nullable().optional(),
});
export type OrderSummary = z.infer<typeof orderSummarySchema>;

export interface ItemInput {
  document_id: string;
  copies: number;
  paper_size: string;
  color_mode: "BW" | "COLOR";
  duplex: boolean;
  options: Record<string, boolean>;
}

export const listShops = (institutionId: string, signal?: AbortSignal) =>
  apiFetch(`/print/shops${toQueryString({ institution_id: institutionId })}`, { schema: z.array(shopSchema), auth: false, signal });

export const getPricing = (shopId: string, signal?: AbortSignal) =>
  apiFetch(`/print/shops/${shopId}/pricing`, { schema: z.array(ruleSchema), auth: false, signal });

export function uploadDocument(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch("/print/documents", { method: "POST", body: form, schema: documentSchema, timeoutMs: 120_000 });
}

export const getQuote = (shopId: string, items: ItemInput[]) =>
  apiFetch("/print/quote", { method: "POST", body: { shop_id: shopId, items }, schema: quoteSchema });

/** expected_total_ugx is only a stale-price guard: the server calculates the real price and refuses if it differs. */
export const createOrder = (
  body: { shop_id: string; items: ItemInput[]; payment_method: "ONLINE" | "PAY_ON_PICKUP"; expected_total_ugx: number },
  idempotencyKey: string,
) => apiFetch("/print/orders", { method: "POST", body, schema: orderSchema, headers: { "Idempotency-Key": idempotencyKey } });

export const listOrders = (page: number, signal?: AbortSignal) =>
  apiFetchPage(`/print/orders${toQueryString({ page, page_size: 10 })}`, { schema: z.array(orderSummarySchema), signal });

export const getOrder = (id: string, signal?: AbortSignal) => apiFetch(`/print/orders/${id}`, { schema: orderSchema, signal });

export const cancelOrder = (id: string, reason?: string) =>
  apiFetch(`/print/orders/${id}/cancel`, { method: "POST", body: { reason }, schema: orderSchema });

/** Options a shop offers, derived from its price list. */
export function describeShop(rules: Rule[]) {
  const perPage = rules.filter((r) => r.kind === "PER_PAGE");
  const paperSizes = [...new Set(perPage.map((r) => r.paper_size ?? ""))].filter(Boolean).sort();
  const colorsFor = (size: string) => [...new Set(perPage.filter((r) => r.paper_size === size).map((r) => r.color_mode))].filter(Boolean) as ("BW" | "COLOR")[];
  const extras = rules
    .filter((r) => r.kind !== "PER_PAGE" && r.option_key)
    .map((r) => ({ key: r.option_key as string, amount: r.amount_ugx, perCopy: r.kind === "PER_COPY" }));
  return { paperSizes, colorsFor, extras };
}
