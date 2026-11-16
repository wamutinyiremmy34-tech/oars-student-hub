import { Link } from "react-router-dom";
import { Card } from "@/components/ui/Card";
import { AccessBadge, StatusBadge } from "@/features/resources/Badges";
import { BookmarkButton } from "@/features/resources/BookmarkButton";
import type { ResourceSummary } from "@/features/resources/api";
import { fileKind, formatBytes } from "@/lib/format";

export function ResourceCard({ resource, showStatus = false }: { resource: ResourceSummary; showStatus?: boolean }) {
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <AccessBadge access={resource.access_type} price={resource.price_ugx} />
        {showStatus && <StatusBadge status={resource.status} />}
        <span className="text-xs text-fg-muted">{resource.category.name}</span>
      </div>
      <h2 className="text-lg font-bold leading-snug">
        <Link to={`/resources/${resource.id}`} className="hover:underline">
          {resource.title}
        </Link>
      </h2>
      {resource.excerpt && <p className="text-sm text-fg-muted">{resource.excerpt}</p>}
      <p className="text-xs text-fg-muted">
        {resource.institution_name}
        {resource.courses.length > 0 && ` · ${resource.courses.map((c) => c.code).join(", ")}`}
        {resource.academic_year ? ` · ${resource.academic_year}` : ""}
        {resource.file ? ` · ${fileKind(resource.file.mime_type)} ${formatBytes(resource.file.size_bytes)}` : ""}
      </p>
      <div className="flex items-center justify-between gap-2">
        <ul className="flex flex-wrap gap-1" aria-label="Tags">
          {resource.tags.slice(0, 3).map((tag) => (
            <li key={tag} className="rounded-full bg-surface px-2 py-0.5 text-xs text-fg-muted">
              #{tag}
            </li>
          ))}
        </ul>
        <BookmarkButton resourceId={resource.id} bookmarked={resource.is_bookmarked} />
      </div>
    </Card>
  );
}
