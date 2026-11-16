import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { ApiError } from "@/lib/api/errors";

/** Only same-site relative paths are allowed as a post-login destination (prevents open redirects). */
export function safeRedirect(target: unknown): string {
  if (typeof target === "string" && target.startsWith("/") && !target.startsWith("//")) {
    return target;
  }
  return "/account";
}

/** Copies server-side field errors (422 details like "body.email") onto the matching form fields. */
export function applyServerFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  knownFields: readonly string[],
): boolean {
  if (!(error instanceof ApiError)) return false;
  let applied = false;
  for (const detail of error.details) {
    const field = detail.field.split(".").pop() ?? "";
    if (knownFields.includes(field)) {
      setError(field as Path<T>, { type: "server", message: detail.message });
      applied = true;
    }
  }
  return applied;
}
