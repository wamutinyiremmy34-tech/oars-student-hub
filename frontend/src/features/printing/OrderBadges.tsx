import { cn } from "@/lib/cn";

const BASE = "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold";

const ORDER_LABEL: Record<string, string> = {
  DRAFT: "Draft",
  SUBMITTED: "Waiting for the shop",
  ACCEPTED: "Accepted",
  PRINTING: "Printing",
  READY_FOR_PICKUP: "Ready for pickup",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
  REJECTED: "Rejected",
};
const PAYMENT_LABEL: Record<string, string> = {
  UNPAID: "Unpaid",
  PENDING: "Payment pending",
  PAID: "Paid",
  FAILED: "Payment failed",
  REFUNDED: "Refunded",
};

export const orderStatusLabel = (status: string) => ORDER_LABEL[status] ?? status;

/** Colour is only a hint: the words always carry the meaning. */
export function OrderStatusBadge({ status }: { status: string }) {
  const tone =
    status === "READY_FOR_PICKUP" || status === "COMPLETED"
      ? "border-accent bg-accent/15"
      : status === "CANCELLED" || status === "REJECTED"
        ? "border-danger bg-danger/10"
        : "border-line bg-surface";
  return <span className={cn(BASE, tone, "text-fg")}>{orderStatusLabel(status)}</span>;
}

export function PaymentStatusBadge({ status, method }: { status: string; method: string }) {
  const label = status === "UNPAID" && method === "PAY_ON_PICKUP" ? "Pay at pickup" : (PAYMENT_LABEL[status] ?? status);
  const tone = status === "PAID" ? "border-accent bg-accent/15" : status === "FAILED" ? "border-danger bg-danger/10" : "border-warning bg-warning/15";
  return <span className={cn(BASE, tone, "text-fg")}>{label}</span>;
}
