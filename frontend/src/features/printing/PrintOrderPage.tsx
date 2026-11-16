import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { createPayment } from "@/features/payments/api";
import { goToCheckout } from "@/features/payments/checkout";
import { cancelOrder, getOrder } from "@/features/printing/api";
import { OrderStatusBadge, PaymentStatusBadge, orderStatusLabel } from "@/features/printing/OrderBadges";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { formatUgx } from "@/lib/format";
import { newKey } from "@/lib/id";

const ACTIVE = new Set(["SUBMITTED", "ACCEPTED", "PRINTING", "READY_FOR_PICKUP"]);

export function PrintOrderPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const query = useQuery({
    queryKey: ["print", "order", id],
    queryFn: ({ signal }) => getOrder(id, signal),
    retry: false,
    // Gentle polling (every 20s) only while the order is still moving, to save mobile data.
    refetchInterval: (q) => (q.state.data && ACTIVE.has(q.state.data.status) ? 20_000 : false),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["print"] });
  const pay = useMutation({
    mutationFn: () => createPayment({ order_id: id }, newKey()),
    onSuccess: (payment) => (payment.checkout_url ? goToCheckout(payment.checkout_url, navigate) : refresh()),
  });
  const cancel = useMutation({ mutationFn: () => cancelOrder(id), onSuccess: refresh });

  if (query.isPending) return <p role="status" className="text-fg-muted">Loading…</p>;
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <Card className="space-y-3">
        <h1 className="text-2xl font-extrabold">{missing ? "Order not found" : "Couldn't load this order"}</h1>
        <p className="text-fg-muted">{missing ? "It doesn't exist or isn't yours." : toUserMessage(query.error)}</p>
        <Link to="/print/orders" className={buttonClasses({ variant: "secondary" })}>My orders</Link>
      </Card>
    );
  }
  const order = query.data;

  return (
    <div className="space-y-6">
      <Card className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <OrderStatusBadge status={order.status} />
          <PaymentStatusBadge status={order.payment_status} method={order.payment_method} />
        </div>
        <h1 className="text-2xl font-extrabold">{order.shop.name}</h1>
        {order.shop.location && <p className="text-fg-muted">{order.shop.location}</p>}
        <p className="text-xl font-extrabold">{formatUgx(order.total_ugx)}</p>

        {order.status === "READY_FOR_PICKUP" && order.pickup_code && (
          <Alert variant="success">
            Your order is ready. Show this pickup code at the shop:{" "}
            <strong className="text-2xl tracking-widest" aria-label="Pickup code">{order.pickup_code}</strong>
            {order.payment_status !== "PAID" && <span className="block">You'll pay {formatUgx(order.total_ugx)} when you collect it.</span>}
          </Alert>
        )}
        {order.status === "REJECTED" && <Alert variant="error">The shop couldn't print this order: {order.reject_reason}</Alert>}
        {order.status === "CANCELLED" && <Alert variant="info">This order was cancelled.{order.payment_status === "PAID" ? " Your payment will be refunded." : ""}</Alert>}
        {order.payment_status === "REFUNDED" && <Alert variant="info">Your payment has been refunded.</Alert>}
      </Card>

      {order.awaiting_payment && (
        <Card className="space-y-3" aria-label="Payment required">
          <h2 className="text-lg font-bold">Payment needed</h2>
          <p className="text-fg-muted">The shop will start once your online payment is confirmed.</p>
          <Button size="lg" onClick={() => pay.mutate()} disabled={pay.isPending}>{pay.isPending ? "Opening checkout…" : "Pay now"}</Button>
          {pay.isError && <Alert variant="error">{toUserMessage(pay.error)}</Alert>}
        </Card>
      )}

      <Card className="space-y-3" aria-label="Documents">
        <h2 className="text-lg font-bold">Documents</h2>
        <ul className="space-y-2">
          {order.items.map((item) => (
            <li key={item.id} className="text-sm">
              <strong>{item.filename}</strong>: {item.page_count} pages × {item.copies}, {item.paper_size}, {item.color_mode === "BW" ? "black and white" : "colour"}
              {item.duplex ? ", double-sided" : ""} · {formatUgx(item.line_total_ugx)}
            </li>
          ))}
        </ul>
      </Card>

      <Card className="space-y-2" aria-label="Progress">
        <h2 className="text-lg font-bold">Progress</h2>
        <ol className="space-y-1 text-sm">
          {order.history.map((h, i) => (
            <li key={i}>{orderStatusLabel(h.to_status)} <span className="text-fg-muted">· {new Date(h.created_at).toLocaleString()}</span>{h.note ? ` · ${h.note}` : ""}</li>
          ))}
        </ol>
      </Card>

      {order.can_cancel && (
        <div className="space-y-2">
          {!confirmCancel ? (
            <Button variant="secondary" onClick={() => setConfirmCancel(true)}>Cancel order</Button>
          ) : (
            <Alert variant="info">
              Cancel this order?{" "}
              <Button variant="danger" onClick={() => cancel.mutate()} disabled={cancel.isPending}>Yes, cancel it</Button>{" "}
              <Button variant="ghost" onClick={() => setConfirmCancel(false)}>Keep it</Button>
            </Alert>
          )}
          {cancel.isError && <Alert variant="error">{toUserMessage(cancel.error)}</Alert>}
        </div>
      )}
    </div>
  );
}
