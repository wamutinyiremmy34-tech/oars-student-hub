import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { startDownload } from "@/lib/navigation";
import { order, orderSummary, SHOP } from "@/test/fixtures";
import { apiError, mockApi, ok, okPage, signedInWith } from "@/test/mock-api";
import { renderApp } from "@/test/render";

vi.mock("@/lib/navigation", () => ({ startDownload: vi.fn(), redirectTo: vi.fn() }));
beforeEach(() => vi.mocked(startDownload).mockClear());

const operator = (extra: string[] = []) => signedInWith(["order:read_any", "order:update_status", "payment:record_cash", ...extra]);
const detailRoute = (body: unknown) => ({ ...operator(), "GET /operator/orders/o-1": () => ok(body) });
const operatorOrder = (o: Record<string, unknown> = {}) => order({ student_name: "Amina Nakato", can_cancel: false, retention_hold: false, ...o });

describe("OperatorQueuePage", () => {
  it("is only for people with the operator permission", async () => {
    mockApi(signedInWith(["order:create"]));
    renderApp("/operator");
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

  it("lists open orders with the student's name and payment state", async () => {
    const api = mockApi({
      ...operator(),
      "GET /operator/shops": () => ok([SHOP]),
      "GET /operator/orders": () => okPage([orderSummary({ student_name: "Amina Nakato" }), orderSummary({ id: "o-2", student_name: "John Okello", payment_method: "ONLINE", payment_status: "PAID", status: "ACCEPTED" })], { page_size: 20 }),
    });
    renderApp("/operator");
    expect(await screen.findByText(/Amina Nakato · 1 document · UGX 300/)).toBeInTheDocument();
    expect(screen.getByText("Pay at pickup")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open order" })[1]).toHaveAttribute("href", "/operator/orders/o-2");

    await userEvent.setup().selectOptions(screen.getByLabelText("Show"), "READY_FOR_PICKUP");
    await waitFor(() => expect(api.callsTo("GET /operator/orders").at(-1)?.search.get("status")).toBe("READY_FOR_PICKUP"));
  });

  it("tells an operator who isn't assigned to a shop what to do", async () => {
    mockApi({ ...operator(), "GET /operator/shops": () => ok([]), "GET /operator/orders": () => okPage([]) });
    renderApp("/operator");
    expect(await screen.findByText(/aren't assigned to a print shop yet/i)).toBeInTheDocument();
    expect(screen.getByText("No orders here right now.")).toBeInTheDocument();
  });
});

describe("OperatorOrderPage", () => {
  it("accepts a pay-on-pickup order straight away", async () => {
    const api = mockApi({ ...detailRoute(operatorOrder()), "POST /operator/orders/o-1/accept": () => ok(operatorOrder({ status: "ACCEPTED" })) });
    renderApp("/operator/orders/o-1");
    expect(await screen.findByRole("heading", { name: "Amina Nakato" })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(api.callsTo("POST /operator/orders/o-1/accept")).toHaveLength(1));
  });

  it("will not accept an online order until the payment is confirmed", async () => {
    mockApi(detailRoute(operatorOrder({ payment_method: "ONLINE", payment_status: "PENDING" })));
    renderApp("/operator/orders/o-1");
    expect(await screen.findByRole("button", { name: "Accept" })).toBeDisabled();
    expect(screen.getByText(/waiting for the student's online payment/i)).toBeInTheDocument();
  });

  it("shows only the next valid action for each status", async () => {
    const cases: [string, string][] = [["ACCEPTED", "Start printing"], ["PRINTING", "Mark ready for pickup"]];
    for (const [status, label] of cases) {
      mockApi(detailRoute(operatorOrder({ status })));
      const view = renderApp("/operator/orders/o-1");
      expect(await screen.findByRole("button", { name: label })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Accept" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Confirm pickup" })).not.toBeInTheDocument();
      view.unmount();
    }
    mockApi(detailRoute(operatorOrder({ status: "COMPLETED", payment_status: "PAID" })));
    renderApp("/operator/orders/o-1");
    expect(await screen.findByText("This order is closed.")).toBeInTheDocument();
  });

  it("requires a reason to reject and sends it", async () => {
    const api = mockApi({ ...detailRoute(operatorOrder()), "POST /operator/orders/o-1/reject": () => ok(operatorOrder({ status: "REJECTED" })) });
    renderApp("/operator/orders/o-1");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Reject…" }));
    const confirm = screen.getByRole("button", { name: "Confirm rejection" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText(/reason for rejecting/i), "Colour unavailable");
    await user.click(confirm);
    await waitFor(() => expect(api.callsTo("POST /operator/orders/o-1/reject")[0]?.body).toEqual({ reason: "Colour unavailable" }));
  });

  it("pay-on-pickup: records the cash first, and only then allows the handover", async () => {
    let paid = false;
    const api = mockApi({
      ...operator(),
      "GET /operator/orders/o-1": () => ok(operatorOrder({ status: "READY_FOR_PICKUP", payment_status: paid ? "PAID" : "UNPAID" })),
      "POST /operator/orders/o-1/payment": () => { paid = true; return ok(operatorOrder({ status: "READY_FOR_PICKUP", payment_status: "PAID" })); },
      "POST /operator/orders/o-1/complete": () => ok(operatorOrder({ status: "COMPLETED", payment_status: "PAID" })),
    });
    renderApp("/operator/orders/o-1");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Customer's pickup code"), "K7QX2M");
    expect(screen.getByRole("button", { name: "Confirm pickup" })).toBeDisabled(); // not paid yet
    expect(screen.getByText("Record the cash payment first.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Record cash payment" }));
    await waitFor(() => expect(api.callsTo("POST /operator/orders/o-1/payment")[0]?.body).toEqual({ amount_ugx: 300 }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm pickup" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Confirm pickup" }));
    await waitFor(() => expect(api.callsTo("POST /operator/orders/o-1/complete")[0]?.body).toEqual({ pickup_code: "K7QX2M" }));
  });

  it("shows the server's refusal of a wrong pickup code", async () => {
    mockApi({
      ...detailRoute(operatorOrder({ status: "READY_FOR_PICKUP", payment_method: "ONLINE", payment_status: "PAID" })),
      "POST /operator/orders/o-1/complete": () => apiError(403, "invalid_pickup_code", "That pickup code is not correct."),
    });
    renderApp("/operator/orders/o-1");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Customer's pickup code"), "WRONG1");
    await user.click(screen.getByRole("button", { name: "Confirm pickup" }));
    expect(await screen.findByText("That pickup code is not correct.")).toBeInTheDocument();
  });

  it("opens a student's document through a short-lived link", async () => {
    const api = mockApi({
      ...detailRoute(operatorOrder()),
      "POST /operator/orders/o-1/items/it-1/document-link": () => ok({ url: "/api/v1/downloads/tok-9", expires_in: 60, filename: "notes.pdf" }),
    });
    renderApp("/operator/orders/o-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Open notes.pdf" }));
    await waitFor(() => expect(startDownload).toHaveBeenCalledWith(expect.stringMatching(/\/api\/v1\/downloads\/tok-9$/)));
    expect(api.callsTo("POST /operator/orders/o-1/items/it-1/document-link")).toHaveLength(1);
  });

  it("says so when a document was deleted after the retention period", async () => {
    mockApi(detailRoute(operatorOrder({ items: [{ ...order().items[0], document_available: false }] })));
    renderApp("/operator/orders/o-1");
    expect(await screen.findByText(/deleted after the retention period/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open notes.pdf" })).not.toBeInTheDocument();
  });

  it("offers the retention hold only to people who may use it", async () => {
    mockApi(detailRoute(operatorOrder()));
    const first = renderApp("/operator/orders/o-1");
    await screen.findByRole("heading", { name: "Amina Nakato" });
    expect(screen.queryByRole("button", { name: /hold documents/i })).not.toBeInTheDocument();
    first.unmount();

    const api = mockApi({ ...signedInWith(["order:read_any", "order:update_status", "order:manage_any"]), "GET /operator/orders/o-1": () => ok(operatorOrder()), "POST /operator/orders/o-1/hold": () => ok({ message: "Retention hold set." }) });
    renderApp("/operator/orders/o-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: /hold documents/i }));
    await waitFor(() => expect(api.callsTo("POST /operator/orders/o-1/hold")[0]?.body).toMatchObject({ hold: true }));
  });

  it("does not reveal orders from other shops", async () => {
    mockApi({ ...operator(), "GET /operator/orders/o-1": () => apiError(404, "not_found") });
    renderApp("/operator/orders/o-1");
    expect(await screen.findByRole("heading", { name: "Order not found" })).toBeInTheDocument();
    expect(screen.getByText(/isn't one of your shop's orders/i)).toBeInTheDocument();
  });
});
