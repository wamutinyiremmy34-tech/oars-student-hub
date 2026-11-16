import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { getPayment, verifyPayment } from "@/features/payments/api";
import { toUserMessage } from "@/lib/api/errors";
import { formatUgx } from "@/lib/format";

/** Where the provider sends the customer back. Arriving here proves NOTHING: this page shows what OUR server
 *  says about the payment, which only changes after the provider's signed webhook (or our own re-check). */
export function PaymentReturnPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["payments", id],
    queryFn: ({ signal }) => getPayment(id, signal),
    refetchInterval: (q) => (q.state.data?.status === "PENDING" ? 3000 : false),
  });
  const check = useMutation({ mutationFn: () => verifyPayment(id), onSuccess: (p) => queryClient.setQueryData(["payments", id], p) });

  if (query.isPending) return <p role="status" className="text-fg-muted">Checking your payment…</p>;
  if (query.isError) return <Alert variant="error">{toUserMessage(query.error)}</Alert>;
  const payment = query.data;
  const next = payment.print_order_id ? `/print/orders/${payment.print_order_id}` : payment.resource_id ? `/resources/${payment.resource_id}` : "/";

  return (
    <Card className="mx-auto max-w-md space-y-4">
      {payment.status === "PAID" && (
        <>
          <h1 className="text-2xl font-extrabold">Payment confirmed</h1>
          <Alert variant="success">We received {formatUgx(payment.amount_ugx)}. Thank you!</Alert>
        </>
      )}
      {payment.status === "PENDING" && (
        <>
          <h1 className="text-2xl font-extrabold">Waiting for confirmation</h1>
          <p role="status" className="text-fg-muted">We haven't heard back from the payment provider yet. This page updates by itself. It can take a minute.</p>
          <Button variant="secondary" onClick={() => check.mutate()} disabled={check.isPending}>Check again</Button>
          {check.isError && <Alert variant="error">{toUserMessage(check.error)}</Alert>}
        </>
      )}
      {payment.status === "FAILED" && (
        <>
          <h1 className="text-2xl font-extrabold">Payment didn't go through</h1>
          <Alert variant="error">No money was taken. You can try again from the order page.</Alert>
        </>
      )}
      {payment.status === "REFUNDED" && <h1 className="text-2xl font-extrabold">This payment was refunded</h1>}
      <Link to={next} className={buttonClasses({ variant: payment.status === "PAID" ? "primary" : "secondary", size: "lg" })}>
        {payment.print_order_id ? "Go to my order" : payment.resource_id ? "Go to the resource" : "Continue"}
      </Link>
    </Card>
  );
}
