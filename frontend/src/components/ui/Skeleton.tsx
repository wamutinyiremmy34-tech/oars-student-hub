/**
 * Skeleton loading placeholder components.
 * Usage: <Skeleton className="h-6 w-32" />
 *        <SkeletonCard />  — a full card skeleton
 *        <SkeletonList n={5} /> — several row skeletons
 */
import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-control bg-line",
        className,
      )}
      aria-hidden="true"
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="rounded-card border border-line bg-raised p-4 space-y-3 animate-pulse" aria-hidden="true">
      <Skeleton className="h-4 w-20" />
      <Skeleton className="h-6 w-3/4" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}

export function SkeletonRow() {
  return (
    <div className="flex items-center gap-3 py-3 animate-pulse" aria-hidden="true">
      <Skeleton className="h-9 w-9 rounded-full shrink-0" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-3 w-1/3" />
      </div>
      <Skeleton className="h-6 w-16 rounded-full" />
    </div>
  );
}

export function SkeletonList({ n = 4 }: { n?: number }) {
  return (
    <div className="divide-y divide-line" aria-hidden="true">
      {Array.from({ length: n }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  );
}

export function SkeletonStatGrid({ cols = 4 }: { cols?: number }) {
  return (
    <div
      className={cn(
        "grid gap-3 animate-pulse",
        cols === 2 && "grid-cols-2",
        cols === 3 && "grid-cols-3",
        cols === 4 && "grid-cols-2 sm:grid-cols-4",
      )}
      aria-hidden="true"
    >
      {Array.from({ length: cols }).map((_, i) => (
        <div key={i} className="rounded-card border border-line bg-raised p-4 space-y-2">
          <Skeleton className="h-8 w-16 mx-auto" />
          <Skeleton className="h-3 w-20 mx-auto" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="rounded-card border border-line overflow-hidden animate-pulse" aria-hidden="true">
      <div className="bg-surface px-3 py-2 flex gap-4">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-4 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="border-t border-line px-3 py-3 flex gap-4">
          {Array.from({ length: cols }).map((_, j) => (
            <Skeleton key={j} className="h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}
