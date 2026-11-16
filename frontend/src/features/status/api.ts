import { z } from "zod";
import { apiFetch } from "@/lib/api/client";

export const readinessSchema = z.object({
  status: z.literal("ready"),
  checks: z.record(z.string(), z.string()),
});

export type Readiness = z.infer<typeof readinessSchema>;

export function getReadiness(signal?: AbortSignal): Promise<Readiness> {
  return apiFetch("/ready", { schema: readinessSchema, signal });
}
