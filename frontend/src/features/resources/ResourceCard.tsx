import { Link } from "react-router-dom";
import { Card } from "@/components/ui/Card";
import { AccessBadge, StatusBadge } from "@/features/resources/Badges";
import { BookmarkButton } from "@/features/resources/BookmarkButton";
import { FileText, Download } from "@/components/ui/Icon";
import type { ResourceSummary } from "@/features/resources/api";
import { fileKind, formatBytes } from "@/lib/format";
import { cn } from "@/lib/cn";

/** Map resource category slug to a background tint for visual differentiation. */
function categoryAccent(categoryName: string): string {
  const name = categoryName.toLowerCase();
  if (name.includes("past paper") || name.includes("exam"))   return "border-t-warning";
  if (name.includes("note") || name.includes("lecture"))       return "border-t-secondary";
  if (name.includes("textbook") || name.includes("book"))      return "border-t-accent";
  if (name.includes("project") || name.includes("thesis"))     return "border-t-primary";
  return "border-t-line";
}

export function ResourceCard({
  resource,
  showStatus = false,
}: {
  resource: ResourceSummary;
  showStatus?: boolean;
}) {
  const accent = categoryAccent(resource.category.name);

  return (
    <Card
      className={cn(
        "flex flex-col gap-3 border-t-4 hover:shadow-lifted transition-shadow",
        accent,
      )}
    >
      {/* Top row: access type, status, category */}
      <div className="flex flex-wrap items-center gap-1.5">
        <AccessBadge access={resource.access_type} price={resource.price_ugx} />
        {showStatus && <StatusBadge status={resource.status} />}
        <span className="ml-auto text-xs text-fg-muted font-medium">{resource.category.name}</span>
      </div>

      {/* Title */}
      <h2 className="text-base font-bold leading-snug line-clamp-2">
        <Link
          to={`/resources/${resource.id}`}
          className="hover:text-brand hover:underline underline-offset-2 transition-colors"
        >
          {resource.title}
        </Link>
      </h2>

      {/* Excerpt */}
      {resource.excerpt && (
        <p className="text-sm text-fg-muted line-clamp-2 leading-relaxed">{resource.excerpt}</p>
      )}

      {/* Meta row */}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-line">
        <div className="flex items-center gap-1.5 min-w-0">
          <FileText size="xs" className="text-fg-muted shrink-0" />
          <span className="text-xs text-fg-muted truncate">
            {resource.institution_name}
            {resource.courses.length > 0 &&
              ` · ${resource.courses.map((c) => c.code).join(", ")}`}
            {resource.file
              ? ` · ${fileKind(resource.file.mime_type)}, ${formatBytes(resource.file.size_bytes)}`
              : ""}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {resource.file && (
            <Download size="xs" className="text-fg-muted" aria-hidden />
          )}
          <BookmarkButton resourceId={resource.id} bookmarked={resource.is_bookmarked} />
        </div>
      </div>

      {/* Tags */}
      {resource.tags.length > 0 && (
        <ul className="flex flex-wrap gap-1" aria-label="Tags">
          {resource.tags.slice(0, 3).map((tag) => (
            <li
              key={tag}
              className="rounded-full bg-surface px-2 py-0.5 text-xs text-fg-muted"
            >
              #{tag}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
