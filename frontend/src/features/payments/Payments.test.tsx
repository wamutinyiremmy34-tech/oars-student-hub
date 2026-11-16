import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { detail, payment } from "@/test/fixtures";
import { apiError, mockApi, ok, signedInWith } from "@/test/mock-api";
import { renderApp } from "@/test/render";

vi.mock("@/lib/navigation", () => ({ startDownload: vi.fn(), redirectTo: vi.fn() }));

const student = () => signedInWith(["order:create", "order:read", "payment:create"]);
const fake = { "GET /payments/config": () => ok({ online_available: true, provider: "fake" }) };

describe("FakeCheckoutPage (development only)", () => {
  it("drives the signed-webhook pipeline through the dev endpoint, then shows what the SERVER says", async () => {
    let status = "PENDING";
    const api = mockApi({
      ...student(), ...fake,
      "GET /payments/p-1": () => ok(payment({ status })),
      "POST /payments/dev/simulate": () => { status = "PAID"; return ok({ status: "PROCESSED" }); },
    });
    renderApp("/pay/fake/p-1");
    expect(await screen.findByRole("heading", { name: /pay UGX 300/i })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Pay now" }));

    expect(api.callsTo("POST /payments/dev/simulate")[0]?.body).toEqual({ payment_id: "p-1", outcome: "success" });
    expect(await screen.findByRole("heading", { name: "Payment confirmed" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to my order" })).toHaveAttribute("href", "/print/orders/o-1");
  });

  it("is not available for a real provider", async () => {
    mockApi({ ...student(), "GET /payments/config": () => ok({ online_available: true, provider: "mtn" }), "GET /payments/p-1": () => ok(payment()) });
    renderApp("/pay/fake/p-1");
    expect(await screen.findByRole("heading", { name: "Not available" })).toBeInTheDocument();
  });
});

describe("PaymentReturnPage", () => {
  it("does not treat arriving on the page as proof of payment", async () => {
    mockApi({ ...student(), "GET /payments/p-1": () => ok(payment({ status: "PENDING" })) });
    renderApp("/payments/p-1");
    expect(await screen.findByRole("heading", { name: "Waiting for confirmation" })).toBeInTheDocument();
    expect(screen.queryByText(/payment confirmed/i)).not.toBeInTheDocument();
  });

  it("re-checks with the server when asked, and updates once the payment is confirmed", async () => {
    const api = mockApi({
      ...student(),
      "GET /payments/p-1": () => ok(payment({ status: "PENDING" })),
      "POST /payments/p-1/verify": () => ok(payment({ status: "PAID", paid_at: "2026-10-08T09:00:00Z" })),
    });
    renderApp("/payments/p-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Check again" }));
    expect(await screen.findByRole("heading", { name: "Payment confirmed" })).toBeInTheDocument();
    expect(api.callsTo("POST /payments/p-1/verify")).toHaveLength(1);
  });

  it("tells the customer when a payment failed and that nothing was charged", async () => {
    mockApi({ ...student(), "GET /payments/p-1": () => ok(payment({ status: "FAILED" })) });
    renderApp("/payments/p-1");
    expect(await screen.findByRole("heading", { name: "Payment didn't go through" })).toBeInTheDocument();
    expect(screen.getByText(/no money was taken/i)).toBeInTheDocument();
  });

  it("links a premium purchase back to the resource", async () => {
    mockApi({ ...student(), "GET /payments/p-9": () => ok(payment({ id: "p-9", status: "PAID", purpose: "RESOURCE_PURCHASE", print_order_id: null, resource_id: "r-1" })) });
    renderApp("/payments/p-9");
    expect(await screen.findByRole("link", { name: "Go to the resource" })).toHaveAttribute("href", "/resources/r-1");
  });
});

describe("buying a premium resource", () => {
  const premium = (config: boolean) => ({
    ...signedInWith([]),
    "GET /resources/r-1": () => ok(detail({ access_type: "PREMIUM", price_ugx: 5000 }, { can_download: false, download_block_reason: "premium_required" })),
    "GET /payments/config": () => ok({ online_available: config, provider: config ? "fake" : null }),
  });

  it("offers a real Buy button when online payment is available and sends no amount", async () => {
    const api = mockApi({
      ...premium(true),
      "POST /payments": () => ok(payment({ purpose: "RESOURCE_PURCHASE", print_order_id: null, resource_id: "r-1", amount_ugx: 5000 }), 201),
      "GET /payments/p-1": () => ok(payment({ amount_ugx: 5000 })),
    });
    renderApp("/resources/r-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Buy for UGX 5,000" }));
    expect(await screen.findByText(/development checkout/i)).toBeInTheDocument();
    expect(api.callsTo("POST /payments")[0]?.body).toEqual({ resource_id: "r-1" });
    expect(screen.queryByRole("button", { name: /download/i })).not.toBeInTheDocument();
  });

  it("is honest when online payment is unavailable", async () => {
    mockApi(premium(false));
    renderApp("/resources/r-1");
    expect(await screen.findByText(/online purchase isn't available yet/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /buy for/i })).not.toBeInTheDocument();
  });

  it("shows why a purchase could not start", async () => {
    mockApi({ ...premium(true), "POST /payments": () => apiError(503, "provider_unavailable") });
    renderApp("/resources/r-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Buy for UGX 5,000" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/temporarily unavailable/i));
  });
});
