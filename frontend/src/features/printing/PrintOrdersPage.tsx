import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SkeletonList } from "@/components/ui/Skeleton";
import { Pagination } from "@/components/ui/Pagination";
import { Plus, Printer, ArrowRight, Package } from "@/components/ui/Icon";
import { listOrders } from "@/features/printing/api";
import { OrderStatusBadge, PaymentStatusBadge } from "@/features/printing/OrderBadges";
import { toUserMessage } from "@/lib/api/errors";
import { formatUgx } from "@/lib/format";

export function PrintOrdersPage() {
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey:        ["print", "orders", page],
    queryFn:         ({ signal }) => listOrders(page, signal),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-extrabold">My print orders</h1>
          <p className="mt-1 text-sm text-fg-muted">Track your printing jobs and order history.</p>
        </div>
        <Link to="/print" className={buttonClasses()}>
          <Plus size="sm" aria-hidden />
          New order
        </Link>
      </div>

      {/* Loading */}
      {query.isPending && (
        <Card>
          <SkeletonList n={5} />
        </Card>
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
            <Printer size="xl" className="text-fg-muted" aria-hidden />
          </div>
          <div className="space-y-1">
            <p className="font-semibold">No print orders yet</p>
            <p className="text-sm text-fg-muted max-w-sm">
              You haven't placed any print orders yet. Submit your first printing order and track it from submission to pickup.
            </p>
          </div>
          <Link to="/print" className={buttonClasses({ variant: "primary" })}>
            <Plus size="sm" aria-hidden />
            Place your first order
          </Link>
        </div>
      )}

      {/* Order list */}
      {query.data && query.data.items.length > 0 && (
        <ul className="space-y-3" aria-label="Print orders">
          {query.data.items.map((order) => (
            <li key={order.id}>
              <Card className="hover:shadow-lifted transition-shadow">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  {/* Left: status badges + shop info */}
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
                      <p className="font-bold leading-snug truncate">{order.shop_name}</p>
                      <p className="text-sm text-fg-muted mt-0.5">
                        {order.item_count} document{order.item_count === 1 ? "" : "s"} ·{" "}
                        {formatUgx(order.total_ugx)}
                      </p>
                      <p className="text-xs text-fg-muted mt-1">
                        {new Date(order.created_at).toLocaleDateString("en-UG", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        })}
                      </p>
                    </div>
                  </div>

                  {/* Right: view link */}
                  <Link
                    to={`/print/orders/${order.id}`}
                    className="shrink-0 inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline"
                  >
                    View order
                    <ArrowRight size="xs" aria-hidden />
                  </Link>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {query.data && (
        <Pagination
          page={page}
          pageSize={10}
          total={query.data.meta.total}
          onChange={setPage}
        />
      )}
    </div>
  );
}
