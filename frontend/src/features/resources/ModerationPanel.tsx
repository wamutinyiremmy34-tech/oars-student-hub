import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { runLifecycle, type LifecycleAction, type ResourceDetail } from "@/features/resources/api";
import { toUserMessage } from "@/lib/api/errors";

/** Buttons are shown from server-computed flags; the API re-checks permission, scope and separation of duties. */
export function ModerationPanel({ resource }: { resource: ResourceDetail }) {
  const queryClient = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const mutation = useMutation({
    mutationFn: ({ action, body }: { action: LifecycleAction; body?: { reason?: string } }) =>
      runLifecycle(resource.id, action, body),
    onSuccess: async () => {
      setRejecting(false);
      setReason("");
      await queryClient.invalidateQueries({ queryKey: ["resources"] });
    },
  });
  const { can_review, can_publish } = resource.viewer;
  const run = (action: LifecycleAction, body?: { reason?: string }) => mutation.mutate({ action, body });

  const actions: ReactElement[] = [];
  if (can_review && resource.status === "SUBMITTED")
    actions.push(<Button key="start" onClick={() => run("start-review")}>Start review</Button>);
  if (can_review && resource.status === "UNDER_REVIEW") {
    actions.push(<Button key="approve" onClick={() => run("approve")}>Approve</Button>);
    actions.push(<Button key="reject" variant="danger" onClick={() => setRejecting(true)}>Reject…</Button>);
  }
  if (can_publish && (resource.status === "APPROVED" || resource.status === "ARCHIVED"))
    actions.push(<Button key="publish" onClick={() => run("publish")}>Publish</Button>);
  if (can_publish && resource.status === "PUBLISHED")
    actions.push(<Button key="archive" variant="secondary" onClick={() => run("archive")}>Archive</Button>);
  if (actions.length === 0 && !rejecting) return null;

  return (
    <Card className="space-y-3" aria-label="Moderation">
      <h2 className="text-lg font-bold">Moderation</h2>
      <div className="flex flex-wrap gap-2">{actions}</div>
      {rejecting && (
        <form
          className="space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (reason.trim().length >= 3) run("reject", { reason: reason.trim() });
          }}
        >
          <label htmlFor="reject-reason" className="block text-sm font-semibold">
            Reason for rejection (the provider will see this)
          </label>
          <textarea id="reject-reason" required minLength={3} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} className="min-h-24 w-full rounded-control border border-line bg-raised p-3" />
          <div className="flex gap-2">
            <Button type="submit" variant="danger" disabled={reason.trim().length < 3 || mutation.isPending}>
              Confirm rejection
            </Button>
            <Button variant="secondary" onClick={() => setRejecting(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {mutation.isError && <Alert variant="error">{toUserMessage(mutation.error)}</Alert>}
    </Card>
  );
}
