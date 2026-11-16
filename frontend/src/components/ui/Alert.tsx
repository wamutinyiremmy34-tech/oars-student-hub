import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type AlertVariant = "error" | "success" | "info";

// Text colours are chosen for WCAG AA contrast on their backgrounds in both themes.
const VARIANTS: Record<AlertVariant, string> = {
  error: "border-danger bg-danger/10 text-danger-strong dark:text-danger",
  success: "border-accent bg-accent/10 text-fg",
  info: "border-secondary bg-secondary/10 text-fg",
};

export function Alert({
  variant = "info",
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & { variant?: AlertVariant }) {
  return (
    <div
      role={variant === "error" ? "alert" : "status"}
      className={cn("rounded-control border px-4 py-3 text-sm font-semibold", VARIANTS[variant], className)}
      {...props}
    />
  );
}
