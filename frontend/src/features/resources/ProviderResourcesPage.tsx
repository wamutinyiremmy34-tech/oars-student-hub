import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { deleteDraft, listMine } from "@/features/resources/api";
import { ResourceCard } from "@/features/resources/ResourceCard";
import { toUserMessage } from "@/lib/api/errors";

export function ProviderResourcesPage() {
  const [page, setPage] = useState(1);
  const [params] = useSearchParams();
  const statusParam = params.get("status") ?? "";
  const [status, setStatus] = useState(statusParam);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ["resources", "mine", page, status],
    queryFn: ({ signal }) => listMine(page, status || undefined, signal),
    placeholderData: keepPreviousData,
  });

  const deleteAction = useMutation({
    mutationFn: (id: string) => deleteDraft(id),
    onSuccess: () => {
      setDeletingId(null);
      qc.invalidateQueries({ queryKey: ["resources", "mine"] });
    },
  });

  function confirmDelete(id: string, title: string) {
    if (window.confirm(`Delete draft "${title}"? This cannot be undone.`)) {
      deleteAction.mutate(id);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">My resources</h1>
        <Link to="/provider/resources/new" className={buttonClasses()}>
          New resource
        </Link>
      </div>
      <div className="max-w-xs">
        <SelectField
          label="Filter by status"
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
        >
          <option value="">All</option>
          <option value="DRAFT">Draft</option>
          <option value="SUBMITTED">Submitted (pending review)</option>
          <option value="UNDER_REVIEW">Under review</option>
          <option value="PUBLISHED">Published</option>
          <option value="REJECTED">Rejected</option>
        </SelectField>
      </div>

      {deleteAction.isError && (
        <Alert variant="error">{toUserMessage(deleteAction.error)}</Alert>
      )}

      {query.isPending && <p role="status" className="text-fg-muted">Loading…</p>}
      {query.isError && (
        <div className="space-y-3">
          <Alert variant="error">{toUserMessage(query.error)}</Alert>
          <Button onClick={() => void query.refetch()}>Try again</Button>
        </div>
      )}
      {query.data?.items.length === 0 && (
        <p className="text-fg-muted">You haven't created any resources yet.</p>
      )}
      {query.data && query.data.items.length > 0 && (
        <>
          <ul className="grid gap-4 md:grid-cols-2">
            {query.data.items.map((resource) => (
              <li key={resource.id} className="space-y-2">
                <ResourceCard resource={resource} showStatus />
                <div className="flex flex-wrap items-center gap-3">
                  <Link
                    to={`/provider/resources/${resource.id}`}
                    className="text-sm font-semibold text-brand underline"
                  >
                    Edit, upload and submit
                  </Link>
                  {resource.status === "DRAFT" && (
                    <button
                      type="button"
                      onClick={() => confirmDelete(resource.id, resource.title)}
                      disabled={deleteAction.isPending && deletingId === resource.id}
                      className="text-sm font-semibold text-danger-strong hover:underline disabled:opacity-50"
                      aria-label={`Delete draft: ${resource.title}`}
                    >
                      {deleteAction.isPending && deletingId === resource.id
                        ? "Deleting…"
                        : "Delete draft"}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <Pagination page={page} pageSize={12} total={query.data.meta.total} onChange={setPage} />
        </>
      )}
    </div>
  );
}
