import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Pagination } from "@/components/ui/Pagination";
import { listMine } from "@/features/resources/api";
import { ResourceCard } from "@/features/resources/ResourceCard";
import { toUserMessage } from "@/lib/api/errors";

export function ProviderResourcesPage() {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["resources", "mine", page],
    queryFn: ({ signal }) => listMine(page, undefined, signal),
    placeholderData: keepPreviousData,
  });
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">My resources</h1>
        <Link to="/provider/resources/new" className={buttonClasses()}>
          New resource
        </Link>
      </div>
      {query.isPending && <p role="status" className="text-fg-muted">Loading…</p>}
      {query.isError && (
        <div className="space-y-3">
          <Alert variant="error">{toUserMessage(query.error)}</Alert>
          <Button onClick={() => void query.refetch()}>Try again</Button>
        </div>
      )}
      {query.data?.items.length === 0 && <p className="text-fg-muted">You haven't created any resources yet.</p>}
      {query.data && query.data.items.length > 0 && (
        <>
          <ul className="grid gap-4 md:grid-cols-2">
            {query.data.items.map((resource) => (
              <li key={resource.id} className="space-y-2">
                <ResourceCard resource={resource} showStatus />
                <Link to={`/provider/resources/${resource.id}`} className="text-sm font-semibold text-brand underline">
                  Edit, upload and submit
                </Link>
              </li>
            ))}
          </ul>
          <Pagination page={page} pageSize={12} total={query.data.meta.total} onChange={setPage} />
        </>
      )}
    </div>
  );
}
