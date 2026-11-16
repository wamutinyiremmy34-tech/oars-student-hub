import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TextField } from "@/components/ui/Field";
import { useAuth } from "@/features/auth/auth-context";
import { getDocumentLink, getOperatorOrder, runOperatorAction, setRetentionHold, type OperatorAction } from "@/features/operator/api";
import { OrderStatusBadge, PaymentStatusBadge } from "@/features/printing/OrderBadges";
import { resolveApiUrl } from "@/lib/api/client";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { formatUgx } from "@/lib/format";
import { startDownload } from "@/lib/navigation";

export function OperatorOrderPage() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [cash, setCash] = useState("");
  const [code, setCode] = useState("");

  const query = useQuery({ queryKey: ["operator", "order", id], queryFn: ({ signal }) => getOperatorOrder(id, signal), retry: false });
  const act = useMutation({
    mutationFn: ({ action, body }: { action: OperatorAction; body?: Record<string, unknown> }) => runOperatorAction(id, action, body),
    onSuccess: async (_data, variables) => {
      setRejecting(false);
      setReason("");
      // Only clear the pickup code after the order is completed, not after recording cash.
      if (variables.action === "complete") setCode("");
      await queryClient.invalidateQueries({ queryKey: ["operator"] });
    },
  });
  const open = useMutation({
    mutationFn: (itemId: string) => getDocumentLink(id, itemId),
    onSuccess: (link) => startDownload(resolveApiUrl(link.url)),
  });
  const hold = useMutation({
    mutationFn: (on: boolean) => setRetentionHold(id, on, on ? "Held by staff" : undefined),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["operator"] }),
  });

  if (query.isPending) return <p role="status" className="text-fg-muted">Loading…</p>;
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <Card className="space-y-3">
        <h1 className="text-2xl font-extrabold">{missing ? "Order not found" : "Couldn't load this order"}</h1>
        <p className="text-fg-muted">{missing ? "It isn't one of your shop's orders." : toUserMessage(query.error)}</p>
        <Link to="/operator" className={buttonClasses({ variant: "secondary" })}>Back to the queue</Link>
      </Card>
    );
  }
  const order = query.data;
  const run = (action: OperatorAction, body?: Record<string, unknown>) => act.mutate({ action, body });
  const waitingForOnlinePayment = order.payment_method === "ONLINE" && order.payment_status !== "PAID";
  const needsCash = order.payment_method === "PAY_ON_PICKUP" && order.payment_status !== "PAID";

  return (
    <div className="space-y-6">
      <Card className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <OrderStatusBadge status={order.status} />
          <PaymentStatusBadge status={order.payment_status} method={order.payment_method} />
          {order.retention_hold && <span className="text-xs font-semibold">Retention hold</span>}
        </div>
        <h1 className="text-2xl font-extrabold">{order.student_name ?? "Student"}</h1>
        <p className="text-xl font-extrabold">{formatUgx(order.total_ugx)}</p>
        <p className="text-sm text-fg-muted">{order.shop.name}</p>
        {order.note && <p>Note: {order.note}</p>}
      </Card>

      <Card className="space-y-3" aria-label="Documents">
        <h2 className="text-lg font-bold">Documents</h2>
        <ul className="space-y-3">
          {order.items.map((item) => (
            <li key={item.id} className="space-y-1 text-sm">
              <p><strong>{item.filename}</strong>: {item.page_count} pages × {item.copies}, {item.paper_size}, {item.color_mode === "BW" ? "black and white" : "colour"}{item.duplex ? ", double-sided" : ""}</p>
              {Object.keys(item.options).length > 0 && <p>Extras: {Object.keys(item.options).join(", ")}</p>}
              {item.document_available ? (
                <Button variant="secondary" onClick={() => open.mutate(item.id)} disabled={open.isPending}>Open {item.filename}</Button>
              ) : (
                <p className="text-fg-muted">This document was deleted after the retention period.</p>
              )}
            </li>
          ))}
        </ul>
        {open.isError && <Alert variant="error">{toUserMessage(open.error)}</Alert>}
      </Card>

      <Card className="space-y-4" aria-label="Actions">
        <h2 className="text-lg font-bold">Actions</h2>
        {order.status === "SUBMITTED" && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              <Button disabled={waitingForOnlinePayment || act.isPending} onClick={() => run("accept")}>Accept</Button>
              <Button variant="danger" onClick={() => setRejecting(true)}>Reject…</Button>
            </div>
            {waitingForOnlinePayment && <p className="text-sm text-fg-muted">Waiting for the student's online payment before this can be accepted.</p>}
          </div>
        )}
        {order.status === "ACCEPTED" && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => run("printing")} disabled={act.isPending}>Start printing</Button>
            <Button variant="danger" onClick={() => setRejecting(true)}>Reject…</Button>
          </div>
        )}
        {order.status === "PRINTING" && <Button onClick={() => run("ready")} disabled={act.isPending}>Mark ready for pickup</Button>}
        {order.status === "READY_FOR_PICKUP" && (
          <div className="space-y-4">
            {needsCash && (
              <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run("payment", { amount_ugx: Number(cash || order.total_ugx) }); }}>
                <TextField label="Cash received (UGX)" inputMode="numeric" value={cash} placeholder={String(order.total_ugx)} onChange={(e) => setCash(e.target.value)} hint={`The order total is ${formatUgx(order.total_ugx)}.`} />
                <Button type="submit" disabled={act.isPending}>Record cash payment</Button>
              </form>
            )}
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run("complete", { pickup_code: code }); }}>
              <TextField label="Customer's pickup code" autoComplete="off" value={code} onChange={(e) => setCode(e.target.value)} />
              <Button type="submit" disabled={needsCash || code.trim().length < 4 || act.isPending}>Confirm pickup</Button>
              {needsCash && <p className="text-sm text-fg-muted">Record the cash payment first.</p>}
            </form>
          </div>
        )}
        {["COMPLETED", "CANCELLED", "REJECTED"].includes(order.status) && <p className="text-fg-muted">This order is closed.</p>}

        {rejecting && (
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (reason.trim().length >= 3) run("reject", { reason: reason.trim() }); }}>
            <TextField label="Reason for rejecting (the student will see this)" value={reason} onChange={(e) => setReason(e.target.value)} />
            <div className="flex gap-2">
              <Button type="submit" variant="danger" disabled={reason.trim().length < 3 || act.isPending}>Confirm rejection</Button>
              <Button variant="ghost" onClick={() => setRejecting(false)}>Cancel</Button>
            </div>
          </form>
        )}
        {act.isError && <Alert variant="error">{toUserMessage(act.error)}</Alert>}
        {can("order:manage_any", order.shop.institution_id) && (
          <Button variant="ghost" onClick={() => hold.mutate(!order.retention_hold)} disabled={hold.isPending}>
            {order.retention_hold ? "Clear retention hold" : "Hold documents (don't delete)"}
          </Button>
        )}
      </Card>
    </div>
  );
}
