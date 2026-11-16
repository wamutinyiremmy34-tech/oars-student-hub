import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { SelectField } from "@/components/ui/Field";
import { listInstitutions } from "@/features/auth/api";
import { useAuth } from "@/features/auth/auth-context";
import { goToCheckout } from "@/features/payments/checkout";
import { createPayment, getPaymentConfig } from "@/features/payments/api";
import {
  createOrder,
  describeShop,
  getPricing,
  getQuote,
  listShops,
  uploadDocument,
  type ItemInput,
  type PrintDocument,
  type Quote,
} from "@/features/printing/api";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { formatBytes, formatUgx } from "@/lib/format";
import { newKey } from "@/lib/id";

const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

interface CartItem extends Omit<ItemInput, "document_id"> {
  doc: PrintDocument;
}

const toInputs = (items: CartItem[]): ItemInput[] =>
  items.map(({ doc, ...rest }) => ({ document_id: doc.id, ...rest, options: Object.fromEntries(Object.entries(rest.options).filter(([, v]) => v)) }));

export function NewPrintOrderPage() {
  const { state } = useAuth();
  const navigate = useNavigate();
  const myInstitution = state.status === "authenticated" ? (state.me.student_profile?.institution_id ?? "") : "";

  const [institutionId, setInstitutionId] = useState(myInstitution);
  const [shopId, setShopId] = useState("");
  const [items, setItems] = useState<CartItem[]>([]);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [method, setMethod] = useState<"PAY_ON_PICKUP" | "ONLINE">("PAY_ON_PICKUP");
  const [message, setMessage] = useState<string | null>(null);
  const idempotencyKey = useRef(newKey());

  const institutions = useQuery({ queryKey: ["institutions"], queryFn: ({ signal }) => listInstitutions(signal), staleTime: 300_000 });
  const shops = useQuery({ queryKey: ["print", "shops", institutionId], queryFn: ({ signal }) => listShops(institutionId, signal), enabled: institutionId !== "" });
  const pricing = useQuery({ queryKey: ["print", "pricing", shopId], queryFn: ({ signal }) => getPricing(shopId, signal), enabled: shopId !== "" });
  const config = useQuery({ queryKey: ["payments", "config"], queryFn: ({ signal }) => getPaymentConfig(signal), staleTime: 60_000 });

  const shop = shops.data?.find((s) => s.id === shopId);
  const offer = describeShop(pricing.data ?? []);
  const onlineAvailable = config.data?.online_available ?? false;

  // Any change to the cart makes the old price and the old idempotency key meaningless.
  const changed = (next: CartItem[]) => {
    setItems(next);
    setQuote(null);
    idempotencyKey.current = newKey();
  };

  useEffect(() => {
    if (shop && !shop.pay_on_pickup_enabled && method === "PAY_ON_PICKUP") setMethod("ONLINE");
  }, [shop, method]);

  const upload = useMutation({
    mutationFn: (file: File) => uploadDocument(file),
    onSuccess: (doc) => {
      const size = offer.paperSizes.includes("A4") ? "A4" : (offer.paperSizes[0] ?? "A4");
      const colors = offer.colorsFor(size);
      changed([...items, { doc, copies: 1, paper_size: size, color_mode: colors.includes("BW") ? "BW" : (colors[0] ?? "BW"), duplex: false, options: {} }]);
    },
  });

  const priceIt = useMutation({
    mutationFn: () => getQuote(shopId, toInputs(items)),
    onSuccess: (q) => {
      setQuote(q);
      setMessage(null);
    },
  });

  const place = useMutation({
    mutationFn: async () => {
      if (!quote) throw new Error("no quote");
      const order = await createOrder({ shop_id: shopId, items: toInputs(items), payment_method: method, expected_total_ugx: quote.total_ugx }, idempotencyKey.current);
      if (method === "ONLINE") {
        try {
          const payment = await createPayment({ order_id: order.id }, `pay-${order.id}`);
          return { order, checkout: payment.checkout_url };
        } catch {
          return { order, checkout: null }; // the order exists; the order page offers "Pay now"
        }
      }
      return { order, checkout: null };
    },
    onSuccess: ({ order, checkout }) => (checkout ? goToCheckout(checkout, navigate) : navigate(`/print/orders/${order.id}`)),
    onError: (error) => {
      if (error instanceof ApiError && error.code === "price_changed") {
        setQuote(null);
        setMessage(`${error.message} Review the new price and try again.`);
      }
    },
  });

  function onFile(file: File | undefined, input: HTMLInputElement) {
    if (!file) return;
    input.value = "";
    if (file.size > MAX_UPLOAD_BYTES) {
      setMessage(`That file is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`);
      return;
    }
    setMessage(null);
    upload.mutate(file);
  }

  const update = (index: number, patch: Partial<CartItem>) =>
    changed(items.map((item, i) => (i === index ? { ...item, ...patch } : item)));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">New print order</h1>
      {message && <Alert variant="info">{message}</Alert>}

      <Card className="space-y-4" aria-label="Choose a print shop">
        <h2 className="text-lg font-bold">1. Choose a print shop</h2>
        <SelectField label="University" value={institutionId} onChange={(e) => { setInstitutionId(e.target.value); setShopId(""); changed([]); }}>
          <option value="">Choose your university</option>
          {institutions.data?.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </SelectField>
        <SelectField label="Print shop" value={shopId} disabled={!institutionId} onChange={(e) => { setShopId(e.target.value); changed([]); }}>
          <option value="">{shops.data?.length === 0 ? "No print shops yet" : "Choose a shop"}</option>
          {shops.data?.map((s) => <option key={s.id} value={s.id}>{s.name}{s.location ? ` (${s.location})` : ""}</option>)}
        </SelectField>
      </Card>

      {shopId && (
        <Card className="space-y-4" aria-label="Documents">
          <h2 className="text-lg font-bold">2. Add your documents</h2>
          <div className="space-y-2">
            <label htmlFor="print-file" className="block text-sm font-semibold">Upload a PDF or image (up to {formatBytes(MAX_UPLOAD_BYTES)})</label>
            <input id="print-file" type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => onFile(e.target.files?.[0], e.target)} className="block w-full text-sm" />
            {upload.isPending && <p role="status" className="text-fg-muted">Uploading…</p>}
            {upload.isError && <Alert variant="error">{toUserMessage(upload.error)}</Alert>}
          </div>

          {items.map((item, index) => (
            <fieldset key={item.doc.id} className="space-y-3 rounded-control border border-line p-3">
              <legend className="px-1 font-semibold">{item.doc.filename} · {item.doc.page_count} page{item.doc.page_count === 1 ? "" : "s"}</legend>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className="block text-sm font-semibold">
                  {`Copies for ${item.doc.filename}`}
                  <input type="number" min={1} max={100} value={item.copies} onChange={(e) => update(index, { copies: Math.min(100, Math.max(1, Number(e.target.value) || 1)) })} className="mt-1 min-h-12 w-full rounded-control border border-line bg-raised px-3" />
                </label>
                <label className="block text-sm font-semibold">
                  {`Paper size for ${item.doc.filename}`}
                  <select value={item.paper_size} onChange={(e) => update(index, { paper_size: e.target.value, color_mode: offer.colorsFor(e.target.value).includes(item.color_mode) ? item.color_mode : (offer.colorsFor(e.target.value)[0] ?? "BW") })} className="mt-1 min-h-12 w-full rounded-control border border-line bg-raised px-3">
                    {offer.paperSizes.map((size) => <option key={size} value={size}>{size}</option>)}
                  </select>
                </label>
                <label className="block text-sm font-semibold">
                  {`Colour for ${item.doc.filename}`}
                  <select value={item.color_mode} onChange={(e) => update(index, { color_mode: e.target.value as "BW" | "COLOR" })} className="mt-1 min-h-12 w-full rounded-control border border-line bg-raised px-3">
                    {offer.colorsFor(item.paper_size).map((c) => <option key={c} value={c}>{c === "BW" ? "Black and white" : "Colour"}</option>)}
                  </select>
                </label>
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-2">
                <label className="flex min-h-11 items-center gap-2 text-sm">
                  <input type="checkbox" checked={item.duplex} onChange={(e) => update(index, { duplex: e.target.checked })} />
                  {`Double-sided for ${item.doc.filename}`}
                </label>
                {offer.extras.map((extra) => (
                  <label key={extra.key} className="flex min-h-11 items-center gap-2 text-sm">
                    <input type="checkbox" checked={Boolean(item.options[extra.key])} onChange={(e) => update(index, { options: { ...item.options, [extra.key]: e.target.checked } })} />
                    {`${extra.key} (+${formatUgx(extra.amount)}${extra.perCopy ? " per copy" : ""}) for ${item.doc.filename}`}
                  </label>
                ))}
              </div>
              <Button variant="ghost" onClick={() => changed(items.filter((_, i) => i !== index))}>Remove {item.doc.filename}</Button>
            </fieldset>
          ))}
        </Card>
      )}

      {items.length > 0 && (
        <Card className="space-y-4" aria-label="Price">
          <h2 className="text-lg font-bold">3. Review the price</h2>
          {!quote ? (
            <>
              <Button size="lg" onClick={() => priceIt.mutate()} disabled={priceIt.isPending}>{priceIt.isPending ? "Calculating…" : "Review price"}</Button>
              {priceIt.isError && <Alert variant="error">{toUserMessage(priceIt.error)}</Alert>}
            </>
          ) : (
            <div className="space-y-2">
              <ul className="space-y-1 text-sm">
                {quote.items.map((i) => (
                  <li key={i.document_id} className="flex justify-between gap-3">
                    <span>{i.filename}: {i.page_count} pages × {i.copies} × {formatUgx(i.unit_price_ugx)}</span>
                    <span>{formatUgx(i.line_total_ugx)}</span>
                  </li>
                ))}
                {quote.order_lines.map((l) => <li key={l.label} className="flex justify-between"><span>{l.label}</span><span>{formatUgx(l.amount_ugx)}</span></li>)}
              </ul>
              <p className="flex justify-between border-t border-line pt-2 text-lg font-extrabold"><span>Total</span><span>{formatUgx(quote.total_ugx)}</span></p>
              <p className="text-xs text-fg-muted">The shop's server calculated this price. It can't be changed from your phone.</p>
            </div>
          )}
        </Card>
      )}

      {quote && (
        <Card className="space-y-4" aria-label="Payment">
          <h2 className="text-lg font-bold">4. Payment</h2>
          <fieldset className="space-y-2">
            <legend className="sr-only">Payment method</legend>
            <label className="flex min-h-11 items-center gap-2">
              <input type="radio" name="method" checked={method === "PAY_ON_PICKUP"} disabled={shop?.pay_on_pickup_enabled === false} onChange={() => { setMethod("PAY_ON_PICKUP"); idempotencyKey.current = newKey(); }} />
              Pay when I collect it
            </label>
            <label className="flex min-h-11 items-center gap-2">
              <input type="radio" name="method" checked={method === "ONLINE"} disabled={!onlineAvailable} onChange={() => { setMethod("ONLINE"); idempotencyKey.current = newKey(); }} />
              Pay online now
            </label>
            {!onlineAvailable && <p className="text-sm text-fg-muted">Online payment isn't available yet.</p>}
            {shop?.pay_on_pickup_enabled === false && <p className="text-sm text-fg-muted">This shop only accepts online payment.</p>}
          </fieldset>
          {place.isError && !(place.error instanceof ApiError && place.error.code === "price_changed") && <Alert variant="error">{toUserMessage(place.error)}</Alert>}
          <Button size="lg" className="w-full sm:w-auto" disabled={place.isPending} onClick={() => place.mutate()}>
            {place.isPending ? "Placing order…" : method === "ONLINE" ? "Place order and pay" : "Place order"}
          </Button>
        </Card>
      )}
    </div>
  );
}
