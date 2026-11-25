import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export type CardVariant = "default" | "flat" | "outlined";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant;
  padding?: "none" | "sm" | "md" | "lg";
}

const PADDING = {
  none: "",
  sm:   "p-3",
  md:   "p-4",
  lg:   "p-6",
};

export function Card({
  className,
  variant = "default",
  padding = "md",
  ...props
}: CardProps) {
  return (
    <div
      className={cn(
        "rounded-card",
        variant === "default"  && "bg-raised border border-line shadow-card",
        variant === "flat"     && "bg-surface border border-line",
        variant === "outlined" && "border border-line",
        PADDING[padding],
        className,
      )}
      {...props}
    />
  );
}
