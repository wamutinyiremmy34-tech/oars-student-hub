import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SelectField } from "@/components/ui/Field";
import { SkeletonList } from "@/components/ui/Skeleton";
import { Pagination } from "@/components/ui/Pagination";
import { Printer, Package, ArrowRight, Clock } from "@/components/ui/Icon";
import { listMyShops, listQueue } from "@/features/operator/api";
import { OrderStatusBadge, PaymentStatusBadge } from "@/features/printing/OrderBadges";
import { toUserMessage } from "@/lib/api/errors";
import { formatUgx } from "@/lib/format";

export function OperatorQueuePage() {
  const [params]            = useSearchParams();
  const [page, setPage]     = useState(1);
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [shopId, setShopId] = useState("");

  const shops = useQuery({
    queryKey: ["operator", "shops"],
    queryFn:  ({ signal }) => listMyShops(signal),
  });

  const queue = useQuery({
    queryKey:        ["operator", "queue", page, status, shopId],
    queryFn:         ({ signal }) => listQueue({ page, status: status || undefined, shop_id: shopId || undefined }, signal),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold">Print queue</h1>
        <p className="mt-1 text-sm text-fg-muted">
          Manage printing jobs for your shop. Auto-refreshes every 30 s.
        </p>
      </div>

      {/* Filters */}
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectField
          label="Shop"
          value={shopId}
          onChange={(e) => { setShopId(e.target.value); setPage(1); }}
        >
          <option value="">All my shops</option>
          {shops.data?.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </SelectField>

        <SelectField
          label="Show"
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
        >
          <option value="">All open orders</option>
          <option value="SUBMITTED">Waiting to be accepted</option>
          <option value="ACCEPTED">Accepted</option>
          <option value="PRINTING">Printing</option>
          <option value="READY_FOR_PICKUP">Ready for pickup</option>
          <option value="COMPLETED">Completed</option>
          <option value="REJECTED">Rejected</option>
          <option value="CANCELLED">Cancelled</option>
        </SelectField>
      </div>

      {/* Not assigned to a shop */}
      {shops.data?.length === 0 && (
        <Alert variant="info">
          You aren't assigned to a print shop yet. Ask an administrator to add you.
        </Alert>
      )}

      {/* Loading */}
      {queue.isPending && (
        <Card>
          <SkeletonList n={5} />
        </Card>
      )}

      {/* Error */}
      {queue.isError && (
        <div className="space-y-3">
          <Alert variant="error">{toUserMessage(queue.error)}</Alert>
          <Button onClick={() => void queue.refetch()}>Try again</Button>
        </div>
      )}

      {/* Empty */}
      {queue.data?.items.length === 0 && (
        <div className="flex flex-col items-center gap-4 py-16 text-center">
          <div className="rounded-full bg-surface p-6">
            <Printer size="xl" className="text-fg-muted" aria-hidden />
          </div>
          <p className="font-semibold">No orders here right now.</p>
          <p className="text-sm text-fg-muted">
            {status ? `No orders with status "${status.replace("_", " ").toLowerCase()}".` : "The queue is empty."}
          </p>
        </div>
      )}

      {/* Order cards */}
      {queue.data && queue.data.items.length > 0 && (
        <>
          <p role="status" className="text-sm text-fg-muted">
            {queue.data.meta.total.toLocaleString()} order{queue.data.meta.total === 1 ? "" : "s"}
          </p>
          <ul className="space-y-3" aria-label="Print orders queue">
            {queue.data.items.map((order) => (
              <li key={order.id}>
                <Card className="hover:shadow-lifted transition-shadow">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="rounded-control bg-surface p-2 shrink-0 mt-0.5">
                        <Package size="sm" className="text-fg-muted" aria-hidden />
                      </div>
                      <div className="min-w-0">
                        <div className="flex flex-wrap gap-1.5 mb-1">
                          <OrderStatusBadge status={order.status} />
                          <PaymentStatusBadge
                            status={order.payment_status}
                            method={order.payment_method}
                          />
                        </div>
                        <p className="font-bold leading-snug">
                          {order.student_name ?? "Student"} · {order.item_count} document{order.item_count === 1 ? "" : "s"} · {formatUgx(order.total_ugx)}
                        </p>
                        <p className="text-sm text-fg-muted">
                          {order.shop_name}
                        </p>
                        <p className="text-xs text-fg-muted mt-1 inline-flex items-center gap-1">
                          <Clock size="xs" aria-hidden />
                          {new Date(order.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>

                    <Link
                      to={`/operator/orders/${order.id}`}
                      className="shrink-0 inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline"
                    >
                      Open order
                      <ArrowRight size="xs" aria-hidden />
                    </Link>
                  </div>
                </Card>
              </li>
            ))}
          </ul>

          <Pagination
            page={page}
            pageSize={20}
            total={queue.data.meta.total}
            onChange={setPage}
          />
        </>
      )}
    </div>
  );
}
