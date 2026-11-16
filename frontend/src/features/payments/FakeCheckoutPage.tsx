import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { getPayment, getPaymentConfig, simulateProvider } from "@/features/payments/api";
import { toUserMessage } from "@/lib/api/errors";
import { formatUgx } from "@/lib/format";

/** DEVELOPMENT ONLY. Stands in for a mobile-money or card checkout page until a real provider is chosen. */
export function FakeCheckoutPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const config = useQuery({ queryKey: ["payments", "config"], queryFn: ({ signal }) => getPaymentConfig(signal) });
  const payment = useQuery({ queryKey: ["payments", id], queryFn: ({ signal }) => getPayment(id, signal), retry: false });
  const simulate = useMutation({
    mutationFn: (outcome: "success" | "failure") => simulateProvider(id, outcome),
    onSuccess: () => navigate(`/payments/${id}`),
  });

  if (config.isSuccess && config.data.provider !== "fake") {
    return <Card><h1 className="text-2xl font-extrabold">Not available</h1><p className="text-fg-muted">This test checkout only exists in development.</p></Card>;
  }
  return (
    <Card className="mx-auto max-w-md space-y-4">
      <Alert variant="info">Development checkout. No real money moves.</Alert>
      <h1 className="text-2xl font-extrabold">Pay {payment.data ? formatUgx(payment.data.amount_ugx) : "…"}</h1>
      {payment.isError && <Alert variant="error">{toUserMessage(payment.error)}</Alert>}
      <div className="flex flex-wrap gap-3">
        <Button size="lg" disabled={!payment.data || simulate.isPending} onClick={() => simulate.mutate("success")}>Pay now</Button>
        <Button size="lg" variant="secondary" disabled={!payment.data || simulate.isPending} onClick={() => simulate.mutate("failure")}>Fail the payment</Button>
      </div>
      {simulate.isError && <Alert variant="error">{toUserMessage(simulate.error)}</Alert>}
    </Card>
  );
}
