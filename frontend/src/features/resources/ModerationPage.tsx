import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { listReviewQueue } from "@/features/resources/api";
import { ResourceCard } from "@/features/resources/ResourceCard";
import { toUserMessage } from "@/lib/api/errors";

export function ModerationPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const query = useQuery({
    queryKey: ["resources", "queue", status, page],
    queryFn: ({ signal }) => listReviewQueue(page, status || undefined, signal),
    placeholderData: keepPreviousData,
  });
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">Moderation queue</h1>
      <div className="max-w-xs">
        <SelectField label="Show" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Needs attention</option>
          <option value="SUBMITTED">Submitted</option>
          <option value="UNDER_REVIEW">Under review</option>
          <option value="APPROVED">Approved (ready to publish)</option>
        </SelectField>
      </div>
      {query.isPending && <p role="status" className="text-fg-muted">Loading…</p>}
      {query.isError && (
        <div className="space-y-3">
          <Alert variant="error">{toUserMessage(query.error)}</Alert>
          <Button onClick={() => void query.refetch()}>Try again</Button>
        </div>
      )}
      {query.data?.items.length === 0 && <p className="text-fg-muted">Nothing to review right now.</p>}
      {query.data && query.data.items.length > 0 && (
        <>
          <ul className="grid gap-4 md:grid-cols-2">
            {query.data.items.map((resource) => (
              <li key={resource.id} className="space-y-2">
                <ResourceCard resource={resource} showStatus />
                <Link to={`/resources/${resource.id}`} className="text-sm font-semibold text-brand underline">Open to review</Link>
              </li>
            ))}
          </ul>
          <Pagination page={page} pageSize={12} total={query.data.meta.total} onChange={setPage} />
        </>
      )}
    </div>
  );
}
