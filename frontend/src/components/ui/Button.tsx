import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "outline";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANTS: Record<ButtonVariant, string> = {
  primary:   "bg-primary text-white hover:bg-primary-hover",
  secondary: "bg-raised text-fg border border-line hover:bg-surface",
  ghost:     "text-brand hover:bg-surface",
  danger:    "bg-danger-strong text-white hover:brightness-110",
  outline:   "border border-primary text-primary hover:bg-brand/5",
};

// min-h-9/11/12 = 36/44/48px: comfortable touch targets.
const SIZES: Record<ButtonSize, string> = {
  sm: "min-h-9  px-3 text-xs",
  md: "min-h-11 px-4 text-sm",
  lg: "min-h-12 px-6 text-base",
};

export function buttonClasses({
  variant = "primary",
  size = "md",
  className,
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
} = {}): string {
  return cn(
    "inline-flex items-center justify-center gap-2 rounded-control font-semibold transition-colors",
    "disabled:cursor-not-allowed disabled:opacity-50",
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-secondary focus-visible:outline-offset-2",
    SIZES[size],
    VARIANTS[variant],
    className,
  );
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export function Button({ variant, size, className, type = "button", ...props }: ButtonProps) {
  return (
    <button
      type={type}
      className={buttonClasses({ variant, size, className })}
      {...props}
    />
  );
}
