import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { listBookmarks } from "@/features/resources/api";
import { ResourceCard } from "@/features/resources/ResourceCard";
import { toUserMessage } from "@/lib/api/errors";

export function BookmarksPage() {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["bookmarks", page],
    queryFn: ({ signal }) => listBookmarks(page, signal),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">Saved resources</h1>
      {query.isPending && <p role="status" className="text-fg-muted">Loading…</p>}
      {query.isError && (
        <div className="space-y-3">
          <Alert variant="error">{toUserMessage(query.error)}</Alert>
          <Button onClick={() => void query.refetch()}>Try again</Button>
        </div>
      )}
      {query.data && query.data.items.length === 0 && (
        <div className="space-y-3">
          <p className="text-fg-muted">You haven't saved anything yet.</p>
          <Link to="/resources" className={buttonClasses()}>Browse resources</Link>
        </div>
      )}
      {query.data && query.data.items.length > 0 && (
        <>
          <ul className="grid gap-4 md:grid-cols-2">
            {query.data.items.map((resource) => (
              <li key={resource.id}>
                <ResourceCard resource={resource} />
              </li>
            ))}
          </ul>
          <Pagination page={page} pageSize={12} total={query.data.meta.total} onChange={setPage} />
        </>
      )}
    </div>
  );
}
