/**
 * Derives provider resource counts and operator queue counts from the
 * existing paginated endpoints. We fetch page 1 with page_size=1 and read
 * the total from the meta — no extra backend endpoints required.
 */
import { z } from "zod";
import { apiFetchPage } from "@/lib/api/client";

const itemSchema = z.unknown();

async function countEndpoint(url: string, signal?: AbortSignal): Promise<number> {
  const result = await apiFetchPage(url, { schema: z.array(itemSchema), signal });
  return result.meta.total;
}

export interface ProviderStats {
  total: number;
  published: number;
  pending: number;
  rejected: number;
  draft: number;
}

export async function getProviderStats(signal?: AbortSignal): Promise<ProviderStats> {
  const [total, published, pending, rejected, draft] = await Promise.all([
    countEndpoint("/resources/mine?page=1&page_size=1", signal),
    countEndpoint("/resources/mine?page=1&page_size=1&status=PUBLISHED", signal),
    countEndpoint("/resources/mine?page=1&page_size=1&status=SUBMITTED", signal),
    countEndpoint("/resources/mine?page=1&page_size=1&status=REJECTED", signal),
    countEndpoint("/resources/mine?page=1&page_size=1&status=DRAFT", signal),
  ]);
  return { total, published, pending, rejected, draft };
}

export interface OperatorStats {
  submitted: number;
  accepted: number;
  printing: number;
  ready: number;
}

export async function getOperatorStats(signal?: AbortSignal): Promise<OperatorStats> {
  const [submitted, accepted, printing, ready] = await Promise.all([
    countEndpoint("/operator/orders?page=1&page_size=1&status=SUBMITTED", signal),
    countEndpoint("/operator/orders?page=1&page_size=1&status=ACCEPTED", signal),
    countEndpoint("/operator/orders?page=1&page_size=1&status=PRINTING", signal),
    countEndpoint("/operator/orders?page=1&page_size=1&status=READY_FOR_PICKUP", signal),
  ]);
  return { submitted, accepted, printing, ready };
}
