import { formatUgx } from "@/lib/format";
import { cn } from "@/lib/cn";

const BASE = "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold";

/** Text stays the default foreground colour so contrast is AA in both themes; meaning is also in the words. */
export function AccessBadge({ access, price }: { access: "FREE" | "PREMIUM"; price: number | null }) {
  return access === "PREMIUM" ? (
    <span className={cn(BASE, "border-warning bg-warning/15 text-fg")}>
      Premium{price ? ` · ${formatUgx(price)}` : ""}
    </span>
  ) : (
    <span className={cn(BASE, "border-accent bg-accent/15 text-fg")}>Free</span>
  );
}

const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Draft",
  SUBMITTED: "Submitted",
  UNDER_REVIEW: "Under review",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  PUBLISHED: "Published",
  ARCHIVED: "Archived",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={cn(BASE, "border-line bg-surface text-fg")}>{STATUS_LABEL[status] ?? status}</span>;
}
