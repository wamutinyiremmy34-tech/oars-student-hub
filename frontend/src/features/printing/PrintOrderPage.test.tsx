import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { order, orderSummary, payment } from "@/test/fixtures";
import { apiError, mockApi, ok, okPage, signedInWith } from "@/test/mock-api";
import { renderApp } from "@/test/render";

vi.mock("@/lib/navigation", () => ({ startDownload: vi.fn(), redirectTo: vi.fn() }));

const student = () => signedInWith(["order:create", "order:read", "payment:create"]);
const show = (body: unknown) => ({ ...student(), "GET /print/orders/o-1": () => ok(body) });

describe("PrintOrderPage", () => {
  it("shows the status, the server's total, the documents and the progress", async () => {
    mockApi(show(order({ status: "PRINTING", can_cancel: false })));
    renderApp("/print/orders/o-1");
    expect(await screen.findByRole("heading", { name: "Main Library Print Shop" })).toBeInTheDocument();
    expect(screen.getByText("Printing")).toBeInTheDocument();
    expect(screen.getByText("UGX 300", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText(/notes\.pdf/)).toBeInTheDocument();
    expect(screen.getByText("Pay at pickup")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel order" })).not.toBeInTheDocument(); // too late to cancel
    expect(screen.queryByLabelText("Pickup code")).not.toBeInTheDocument();
  });

  it("shows the pickup code only when the server provides it (order ready)", async () => {
    mockApi(show(order({ status: "READY_FOR_PICKUP", can_cancel: false, pickup_code: "K7QX2M" })));
    renderApp("/print/orders/o-1");
    expect(await screen.findByLabelText("Pickup code")).toHaveTextContent("K7QX2M");
    expect(screen.getByText(/you'll pay UGX 300 when you collect it/i)).toBeInTheDocument();
  });

  it("offers Pay now for an online order that is waiting for payment and opens the checkout", async () => {
    const api = mockApi({
      ...show(order({ payment_method: "ONLINE", awaiting_payment: true })),
      "POST /payments": () => ok(payment(), 201),
      "GET /payments/p-1": () => ok(payment()),
      "GET /payments/config": () => ok({ online_available: true, provider: "fake" }),
    });
    renderApp("/print/orders/o-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Pay now" }));
    expect(await screen.findByText(/development checkout/i)).toBeInTheDocument();
    expect(api.callsTo("POST /payments")[0]?.body).toEqual({ order_id: "o-1" });
    expect(api.callsTo("POST /payments")[0]?.headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("explains when the payment provider is unavailable", async () => {
    mockApi({ ...show(order({ payment_method: "ONLINE", awaiting_payment: true })), "POST /payments": () => apiError(503, "provider_unavailable") });
    renderApp("/print/orders/o-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Pay now" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/temporarily unavailable/i);
  });

  it("asks for confirmation before cancelling, then shows the updated order", async () => {
    let cancelled = false;
    const api = mockApi({
      ...student(),
      "GET /print/orders/o-1": () => ok(cancelled ? order({ status: "CANCELLED", can_cancel: false }) : order()),
      "POST /print/orders/o-1/cancel": () => { cancelled = true; return ok(order({ status: "CANCELLED", can_cancel: false })); },
    });
    renderApp("/print/orders/o-1");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Cancel order" }));
    expect(api.callsTo("POST /print/orders/o-1/cancel")).toHaveLength(0); // not yet
    await user.click(screen.getByRole("button", { name: "Yes, cancel it" }));
    expect(await screen.findByText(/this order was cancelled/i)).toBeInTheDocument();
  });

  it("explains a rejected order and a refunded payment", async () => {
    mockApi(show(order({ status: "REJECTED", can_cancel: false, reject_reason: "Colour printing is unavailable today" })));
    const first = renderApp("/print/orders/o-1");
    expect(await screen.findByText(/colour printing is unavailable today/i)).toBeInTheDocument();
    first.unmount();

    mockApi(show(order({ status: "CANCELLED", payment_status: "PAID", payment_method: "ONLINE", can_cancel: false })));
    renderApp("/print/orders/o-1");
    expect(await screen.findByText(/your payment will be refunded/i)).toBeInTheDocument();
  });

  it("shows a friendly page for orders that aren't yours", async () => {
    mockApi({ ...student(), "GET /print/orders/o-1": () => apiError(404, "not_found") });
    renderApp("/print/orders/o-1");
    expect(await screen.findByRole("heading", { name: "Order not found" })).toBeInTheDocument();
  });

  it("is only for signed-in customers", async () => {
    mockApi({ "POST /auth/refresh": () => apiError(401, "invalid_refresh_token") });
    renderApp("/print/orders/o-1");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("PrintOrdersPage", () => {
  it("lists my orders with status and payment", async () => {
    mockApi({
      ...student(),
      "GET /print/orders": () => okPage([orderSummary(), orderSummary({ id: "o-2", status: "COMPLETED", payment_status: "PAID", total_ugx: 500 })], { page_size: 10 }),
    });
    renderApp("/print/orders");
    expect(await screen.findByText("Waiting for the shop")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "View order" })[1]).toHaveAttribute("href", "/print/orders/o-2");
  });

  it("shows an empty state and paginates", async () => {
    mockApi({ ...student(), "GET /print/orders": () => okPage([]) });
    const first = renderApp("/print/orders");
    expect(await screen.findByText(/haven't placed any print orders/i)).toBeInTheDocument();
    first.unmount();

    const api = mockApi({ ...student(), "GET /print/orders": () => okPage([orderSummary()], { page: 1, page_size: 10, total: 25 }) });
    renderApp("/print/orders");
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(api.callsTo("GET /print/orders").at(-1)?.search.get("page")).toBe("2"));
  });
});
