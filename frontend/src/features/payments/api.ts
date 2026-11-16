import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

export const paymentSchema = z.object({
  id: z.string(),
  purpose: z.string(),
  status: z.enum(["PENDING", "PAID", "FAILED", "REFUNDED"]),
  method: z.string(),
  provider: z.string(),
  amount_ugx: z.number(),
  currency: z.string(),
  checkout_url: z.string().nullable(),
  print_order_id: z.string().nullable(),
  resource_id: z.string().nullable(),
  failure_reason: z.string().nullable(),
  created_at: z.string(),
  paid_at: z.string().nullable(),
});
export type Payment = z.infer<typeof paymentSchema>;

const configSchema = z.object({ online_available: z.boolean(), provider: z.string().nullable() });

export function getPaymentConfig(signal?: AbortSignal) {
  return apiFetch("/payments/config", { schema: configSchema, auth: false, signal });
}

/** The amount is never sent: the server reads it from the order or resource. */
export function createPayment(target: { order_id: string } | { resource_id: string }, idempotencyKey: string) {
  return apiFetch("/payments", { method: "POST", body: target, schema: paymentSchema, headers: { "Idempotency-Key": idempotencyKey } });
}

export function getPayment(id: string, signal?: AbortSignal) {
  return apiFetch(`/payments/${id}`, { schema: paymentSchema, signal });
}

export function verifyPayment(id: string) {
  return apiFetch(`/payments/${id}/verify`, { method: "POST", schema: paymentSchema });
}

/** Development only (the server returns 404 in production). Drives the real signed-webhook pipeline. */
export function simulateProvider(paymentId: string, outcome: "success" | "failure") {
  return apiFetch("/payments/dev/simulate", {
    method: "POST",
    body: { payment_id: paymentId, outcome },
    schema: z.object({ status: z.string() }),
  });
}
