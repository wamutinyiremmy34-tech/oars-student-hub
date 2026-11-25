/**
 * Lightweight toast / snackbar system.
 *
 * Usage:
 *   const toast = useToast();
 *   toast.success("Saved!");
 *   toast.error("Something went wrong.");
 *
 * Mount <Toaster /> once inside the app shell.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { CheckCircle, XCircle, Info, AlertCircle, X } from "@/components/ui/Icon";

// ─── Types ────────────────────────────────────────────────────────────────────

export type ToastVariant = "success" | "error" | "info" | "warning";

export interface Toast {
  id: string;
  variant: ToastVariant;
  message: string;
  duration?: number; // ms, default 4000
}

interface ToastContextValue {
  add: (toast: Omit<Toast, "id">) => void;
  remove: (id: string) => void;
}

// ─── Context ──────────────────────────────────────────────────────────────────

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const remove = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const add = useCallback((toast: Omit<Toast, "id">) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev.slice(-4), { ...toast, id }]); // keep at most 5
    const duration = toast.duration ?? 4000;
    setTimeout(() => remove(id), duration);
  }, [remove]);

  return (
    <ToastContext.Provider value={{ add, remove }}>
      {children}
      <Toaster toasts={toasts} onRemove={remove} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");

  return {
    success: (message: string, duration?: number) => ctx.add({ variant: "success", message, duration }),
    error:   (message: string, duration?: number) => ctx.add({ variant: "error", message, duration: duration ?? 6000 }),
    info:    (message: string, duration?: number) => ctx.add({ variant: "info", message, duration }),
    warning: (message: string, duration?: number) => ctx.add({ variant: "warning", message, duration }),
    add:     ctx.add,
    remove:  ctx.remove,
  };
}

// ─── Individual toast item ────────────────────────────────────────────────────

const VARIANT_STYLES: Record<ToastVariant, string> = {
  success: "border-l-accent bg-raised text-fg",
  error:   "border-l-danger bg-raised text-fg",
  info:    "border-l-secondary bg-raised text-fg",
  warning: "border-l-warning bg-raised text-fg",
};

function ToastIcon({ variant }: { variant: ToastVariant }) {
  const cls = {
    success: "text-accent",
    error:   "text-danger-strong",
    info:    "text-secondary",
    warning: "text-warning",
  }[variant];

  const Icon = {
    success: CheckCircle,
    error:   XCircle,
    info:    Info,
    warning: AlertCircle,
  }[variant];

  return <Icon size="sm" className={cls} aria-hidden />;
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // small delay so the enter transition runs
    const t = setTimeout(() => setVisible(true), 10);
    return () => clearTimeout(t);
  }, []);

  return (
    <div
      ref={ref}
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-start gap-3 rounded-card border-l-4 px-4 py-3 shadow-lifted min-w-64 max-w-sm w-full",
        "transition-all duration-200",
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2",
        VARIANT_STYLES[toast.variant],
      )}
    >
      <ToastIcon variant={toast.variant} />
      <p className="flex-1 text-sm leading-snug">{toast.message}</p>
      <button
        type="button"
        aria-label="Dismiss notification"
        onClick={() => onRemove(toast.id)}
        className="shrink-0 rounded-control p-0.5 hover:bg-surface text-fg-muted hover:text-fg transition-colors"
      >
        <X size="xs" />
      </button>
    </div>
  );
}

// ─── Toaster container ────────────────────────────────────────────────────────

function Toaster({ toasts, onRemove }: { toasts: Toast[]; onRemove: (id: string) => void }) {
  if (toasts.length === 0) return null;
  return (
    <div
      aria-label="Notifications"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 items-end pointer-events-none"
    >
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <ToastItem toast={t} onRemove={onRemove} />
        </div>
      ))}
    </div>
  );
}
