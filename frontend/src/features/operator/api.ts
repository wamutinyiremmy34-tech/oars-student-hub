import { z } from "zod";
import { apiFetch, apiFetchPage } from "@/lib/api/client";
import { toQueryString } from "@/features/resources/api";
import { orderSchema, orderSummarySchema, shopSchema } from "@/features/printing/api";

export const listMyShops = (signal?: AbortSignal) => apiFetch("/operator/shops", { schema: z.array(shopSchema), signal });

export const listQueue = (params: { page: number; status?: string; shop_id?: string }, signal?: AbortSignal) =>
  apiFetchPage(`/operator/orders${toQueryString({ ...params, page_size: 20 })}`, { schema: z.array(orderSummarySchema), signal });

export const getOperatorOrder = (id: string, signal?: AbortSignal) => apiFetch(`/operator/orders/${id}`, { schema: orderSchema, signal });

export type OperatorAction = "accept" | "reject" | "printing" | "ready" | "payment" | "complete";

export const runOperatorAction = (id: string, action: OperatorAction, body: Record<string, unknown> = {}) =>
  apiFetch(`/operator/orders/${id}/${action}`, { method: "POST", body, schema: orderSchema });

export const getDocumentLink = (orderId: string, itemId: string) =>
  apiFetch(`/operator/orders/${orderId}/items/${itemId}/document-link`, {
    method: "POST",
    schema: z.object({ url: z.string(), expires_in: z.number(), filename: z.string() }),
  });

export const setRetentionHold = (id: string, hold: boolean, reason?: string) =>
  apiFetch(`/operator/orders/${id}/hold`, { method: "POST", body: { hold, reason }, schema: z.object({ message: z.string() }) });
