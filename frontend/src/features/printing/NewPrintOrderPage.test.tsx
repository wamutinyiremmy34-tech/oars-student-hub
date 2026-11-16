import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DOC, INSTITUTIONS, order, payment, QUOTE, RULES, SHOP } from "@/test/fixtures";
import { apiError, mockApi, ok, signedInWith } from "@/test/mock-api";
import { renderApp } from "@/test/render";

vi.mock("@/lib/navigation", () => ({ startDownload: vi.fn(), redirectTo: vi.fn() }));

const student = () => signedInWith(["order:create", "order:read", "payment:create"]);
const routes = (online = true) => ({
  ...student(),
  "GET /institutions": () => ok(INSTITUTIONS),
  "GET /print/shops": () => ok([SHOP]),
  "GET /print/shops/s-1/pricing": () => ok(RULES),
  "GET /payments/config": () => ok({ online_available: online, provider: online ? "fake" : null }),
  "POST /print/documents": () => ok(DOC, 201),
  "POST /print/quote": () => ok(QUOTE),
  "POST /print/orders": () => ok(order(), 201),
  "GET /print/orders/o-1": () => ok(order()),
});

const pdf = () => new File(["%PDF-1.4"], "notes.pdf", { type: "application/pdf" });

async function addDocument(user = userEvent.setup()) {
  await user.selectOptions(await screen.findByLabelText("Print shop"), "s-1");
  await user.upload(await screen.findByLabelText(/upload a pdf or image/i), pdf());
  await screen.findByText(/notes\.pdf · 3 pages/);
  return user;
}

describe("NewPrintOrderPage", () => {
  it("starts from the student's university and offers only what the shop's price list allows", async () => {
    const api = mockApi(routes());
    renderApp("/print");
    expect(await screen.findByRole("heading", { name: "New print order" })).toBeInTheDocument();
    await waitFor(() => expect(api.callsTo("GET /print/shops")[0]?.search.get("institution_id")).toBe("i-1"));
    await addDocument();
    expect(screen.getByLabelText("Paper size for notes.pdf")).toHaveValue("A4");
    const colour = screen.getByLabelText("Colour for notes.pdf");
    expect(within(colour).getAllByRole("option").map((o) => o.textContent)).toEqual(["Black and white", "Colour"]);
    expect(screen.getByLabelText(/staple \(\+UGX 100 per copy\)/i)).toBeInTheDocument();
  });

  it("shows the price the SERVER calculated and discards it when the cart changes", async () => {
    const api = mockApi(routes());
    renderApp("/print");
    const user = await addDocument();
    await user.click(screen.getByRole("button", { name: "Review price" }));
    expect(await screen.findAllByText("UGX 150")).toHaveLength(2); // the line item and the total
    expect(api.callsTo("POST /print/quote")[0]?.body).toEqual({
      shop_id: "s-1", items: [{ document_id: "d-1", copies: 1, paper_size: "A4", color_mode: "BW", duplex: false, options: {} }],
    });

    await user.clear(screen.getByLabelText("Copies for notes.pdf"));
    await user.type(screen.getByLabelText("Copies for notes.pdf"), "2");
    expect(await screen.findByRole("button", { name: "Review price" })).toBeInTheDocument(); // the old price is no longer valid
    expect(screen.queryByRole("button", { name: "Place order" })).not.toBeInTheDocument();
  });

  it("places a pay-on-pickup order without ever sending a price, and tracks it with a retry-safe key", async () => {
    const api = mockApi(routes());
    renderApp("/print");
    const user = await addDocument();
    await user.click(screen.getByRole("button", { name: "Review price" }));
    await user.click(await screen.findByRole("button", { name: "Place order" }));

    expect(await screen.findByRole("heading", { name: "Main Library Print Shop" })).toBeInTheDocument();
    const call = api.callsTo("POST /print/orders")[0]!;
    expect(call.body).toEqual({
      shop_id: "s-1", payment_method: "PAY_ON_PICKUP", expected_total_ugx: 150,
      items: [{ document_id: "d-1", copies: 1, paper_size: "A4", color_mode: "BW", duplex: false, options: {} }],
    });
    expect(JSON.stringify(call.body)).not.toMatch(/unit_price|line_total|"total_ugx"/); // no client-side prices
    expect(call.headers.get("Idempotency-Key")).toBeTruthy();
    expect(api.callsTo("POST /payments")).toHaveLength(0);
  });

  it("reuses the same Idempotency-Key when retrying an unchanged order", async () => {
    let attempts = 0;
    const api = mockApi({ ...routes(), "POST /print/orders": () => (++attempts === 1 ? apiError(503, "service_unavailable") : ok(order(), 201)) });
    renderApp("/print");
    const user = await addDocument();
    await user.click(screen.getByRole("button", { name: "Review price" }));
    await user.click(await screen.findByRole("button", { name: "Place order" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/temporarily unavailable/i);
    await user.click(screen.getByRole("button", { name: "Place order" }));
    await screen.findByRole("heading", { name: "Main Library Print Shop" });
    const [first, second] = api.callsTo("POST /print/orders");
    expect(first?.headers.get("Idempotency-Key")).toBe(second?.headers.get("Idempotency-Key"));
  });

  it("creates the order, then a payment for it, then opens the checkout when paying online", async () => {
    const api = mockApi({
      ...routes(),
      "POST /print/orders": () => ok(order({ payment_method: "ONLINE", awaiting_payment: true }), 201),
      "POST /payments": () => ok(payment(), 201),
      "GET /payments/p-1": () => ok(payment()),
    });
    renderApp("/print");
    const user = await addDocument();
    await user.click(screen.getByRole("button", { name: "Review price" }));
    await user.click(await screen.findByLabelText("Pay online now"));
    await user.click(screen.getByRole("button", { name: "Place order and pay" }));

    expect(await screen.findByText(/development checkout/i)).toBeInTheDocument();
    expect(api.callsTo("POST /payments")[0]?.body).toEqual({ order_id: "o-1" }); // the amount is not sent
  });

  it("disables online payment while it is unavailable", async () => {
    mockApi(routes(false));
    renderApp("/print");
    const user = await addDocument();
    await user.click(screen.getByRole("button", { name: "Review price" }));
    expect(await screen.findByLabelText("Pay online now")).toBeDisabled();
    expect(screen.getByText(/online payment isn't available yet/i)).toBeInTheDocument();
  });

  it("asks the student to review a changed price instead of charging it", async () => {
    mockApi({ ...routes(), "POST /print/orders": () => apiError(409, "price_changed", "The price changed to UGX 200.") });
    renderApp("/print");
    const user = await addDocument();
    await user.click(screen.getByRole("button", { name: "Review price" }));
    await user.click(await screen.findByRole("button", { name: "Place order" }));
    expect(await screen.findByText(/price changed to UGX 200/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Review price" })).toBeInTheDocument();
  });

  it("checks file size in the browser and shows server-side rejections", async () => {
    const api = mockApi({ ...routes(), "POST /print/documents": () => apiError(415, "unreadable_pdf", "This PDF could not be read.") });
    renderApp("/print");
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Print shop"), "s-1");
    const input = await screen.findByLabelText(/upload a pdf or image/i);

    const huge = new File(["x"], "huge.pdf", { type: "application/pdf" });
    Object.defineProperty(huge, "size", { value: 26 * 1024 * 1024 });
    await user.upload(input, huge);
    expect(await screen.findByText(/the limit is 25\.0 MB/i)).toBeInTheDocument();
    expect(api.callsTo("POST /print/documents")).toHaveLength(0);

    await user.upload(input, pdf());
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be read/i);
  });
});
