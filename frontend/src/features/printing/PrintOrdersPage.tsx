import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Pagination } from "@/components/ui/Pagination";
import { listOrders } from "@/features/printing/api";
import { OrderStatusBadge, PaymentStatusBadge } from "@/features/printing/OrderBadges";
import { toUserMessage } from "@/lib/api/errors";
import { formatUgx } from "@/lib/format";

export function PrintOrdersPage() {
  const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: ["print", "orders", page], queryFn: ({ signal }) => listOrders(page, signal), placeholderData: keepPreviousData });
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">My print orders</h1>
        <Link to="/print" className={buttonClasses()}>New order</Link>
      </div>
      {query.isPending && <p role="status" className="text-fg-muted">Loading…</p>}
      {query.isError && (
        <div className="space-y-3">
          <Alert variant="error">{toUserMessage(query.error)}</Alert>
          <Button onClick={() => void query.refetch()}>Try again</Button>
        </div>
      )}
      {query.data?.items.length === 0 && <p className="text-fg-muted">You haven't placed any print orders yet.</p>}
      <ul className="space-y-3">
        {query.data?.items.map((order) => (
          <li key={order.id}>
            <Card className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <OrderStatusBadge status={order.status} />
                <PaymentStatusBadge status={order.payment_status} method={order.payment_method} />
              </div>
              <p className="font-bold">{order.shop_name} · {order.item_count} document{order.item_count === 1 ? "" : "s"} · {formatUgx(order.total_ugx)}</p>
              <p className="text-sm text-fg-muted">{new Date(order.created_at).toLocaleString()}</p>
              <Link to={`/print/orders/${order.id}`} className="font-semibold text-brand underline">View order</Link>
            </Card>
          </li>
        ))}
      </ul>
      {query.data && <Pagination page={page} pageSize={10} total={query.data.meta.total} onChange={setPage} />}
    </div>
  );
}
