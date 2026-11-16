import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SelectField } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { listMyShops, listQueue } from "@/features/operator/api";
import { OrderStatusBadge, PaymentStatusBadge } from "@/features/printing/OrderBadges";
import { toUserMessage } from "@/lib/api/errors";
import { formatUgx } from "@/lib/format";

export function OperatorQueuePage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [shopId, setShopId] = useState("");
  const shops = useQuery({ queryKey: ["operator", "shops"], queryFn: ({ signal }) => listMyShops(signal) });
  const queue = useQuery({
    queryKey: ["operator", "queue", page, status, shopId],
    queryFn: ({ signal }) => listQueue({ page, status: status || undefined, shop_id: shopId || undefined }, signal),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000, // new orders appear without reloading, at a data-friendly pace
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">Print queue</h1>
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectField label="Shop" value={shopId} onChange={(e) => { setShopId(e.target.value); setPage(1); }}>
          <option value="">All my shops</option>
          {shops.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </SelectField>
        <SelectField label="Show" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Open orders</option>
          <option value="SUBMITTED">Waiting to be accepted</option>
          <option value="ACCEPTED">Accepted</option>
          <option value="PRINTING">Printing</option>
          <option value="READY_FOR_PICKUP">Ready for pickup</option>
          <option value="COMPLETED">Completed</option>
          <option value="REJECTED">Rejected</option>
          <option value="CANCELLED">Cancelled</option>
        </SelectField>
      </div>
      {shops.data?.length === 0 && <Alert variant="info">You aren't assigned to a print shop yet. Ask an administrator to add you.</Alert>}
      {queue.isPending && <p role="status" className="text-fg-muted">Loading…</p>}
      {queue.isError && (
        <div className="space-y-3">
          <Alert variant="error">{toUserMessage(queue.error)}</Alert>
          <Button onClick={() => void queue.refetch()}>Try again</Button>
        </div>
      )}
      {queue.data?.items.length === 0 && <p className="text-fg-muted">No orders here right now.</p>}
      <ul className="space-y-3">
        {queue.data?.items.map((order) => (
          <li key={order.id}>
            <Card className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <OrderStatusBadge status={order.status} />
                <PaymentStatusBadge status={order.payment_status} method={order.payment_method} />
              </div>
              <p className="font-bold">{order.student_name ?? "Student"} · {order.item_count} document{order.item_count === 1 ? "" : "s"} · {formatUgx(order.total_ugx)}</p>
              <p className="text-sm text-fg-muted">{order.shop_name} · {new Date(order.created_at).toLocaleString()}</p>
              <Link to={`/operator/orders/${order.id}`} className="font-semibold text-brand underline">Open order</Link>
            </Card>
          </li>
        ))}
      </ul>
      {queue.data && <Pagination page={page} pageSize={20} total={queue.data.meta.total} onChange={setPage} />}
    </div>
  );
}
