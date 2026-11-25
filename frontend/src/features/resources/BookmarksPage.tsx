import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { SkeletonCard } from "@/components/ui/Skeleton";
import { Pagination } from "@/components/ui/Pagination";
import { Bookmark, BookOpen, ArrowRight } from "@/components/ui/Icon";
import { listBookmarks } from "@/features/resources/api";
import { ResourceCard } from "@/features/resources/ResourceCard";
import { toUserMessage } from "@/lib/api/errors";

export function BookmarksPage() {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey:        ["bookmarks", page],
    queryFn:         ({ signal }) => listBookmarks(page, signal),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold flex items-center gap-2">
          <Bookmark size="lg" className="text-brand" aria-hidden />
          Saved resources
        </h1>
        {query.data && query.data.meta.total > 0 && (
          <p className="mt-1 text-sm text-fg-muted">
            {query.data.meta.total} saved resource{query.data.meta.total !== 1 ? "s" : ""}
          </p>
        )}
      </div>

      {/* Loading */}
      {query.isPending && (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {/* Error */}
      {query.isError && (
        <div className="space-y-3">
          <Alert variant="error">{toUserMessage(query.error)}</Alert>
          <Button onClick={() => void query.refetch()}>Try again</Button>
        </div>
      )}

      {/* Empty state */}
      {query.data?.items.length === 0 && (
        <div className="flex flex-col items-center gap-4 py-16 text-center">
          <div className="rounded-full bg-surface p-6">
            <BookOpen size="xl" className="text-fg-muted" aria-hidden />
          </div>
          <div className="space-y-1">
            <p className="font-semibold">You haven't saved anything yet.</p>
            <p className="text-sm text-fg-muted max-w-sm">
              Bookmark resources to save them for later. Look for the bookmark icon on any resource card.
            </p>
          </div>
          <Link to="/resources" className={buttonClasses({ variant: "primary" })}>
            Browse resources
            <ArrowRight size="sm" aria-hidden />
          </Link>
        </div>
      )}

      {/* Resource grid */}
      {query.data && query.data.items.length > 0 && (
        <>
          <ul className="grid gap-4 md:grid-cols-2" aria-label="Saved resources">
            {query.data.items.map((resource) => (
              <li key={resource.id}>
                <ResourceCard resource={resource} />
              </li>
            ))}
          </ul>
          <Pagination
            page={page}
            pageSize={12}
            total={query.data.meta.total}
            onChange={setPage}
          />
        </>
      )}
    </div>
  );
}
