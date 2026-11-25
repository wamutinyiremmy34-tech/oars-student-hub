/**
 * PrintShopPanel — Admin UI for managing print shops, pricing rules, and operators.
 * Uses: GET/POST/PATCH /print/shops, GET/POST/PATCH /print/shops/:id/pricing-rules
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TextField, SelectField } from "@/components/ui/Field";
import { listInstitutions as listAuthInstitutions } from "@/features/auth/api";
import {
  listShopsAdmin,
  createShop,
  updateShop,
  listPricingRules,
  addPricingRule,
  updatePricingRule,
  listAllOrders,
  type Shop,
} from "@/features/admin/api";
import { OrderStatusBadge } from "@/features/printing/OrderBadges";
import { formatUgx } from "@/lib/format";
import { toUserMessage } from "@/lib/api/errors";

// ─── Shop form ────────────────────────────────────────────────────────────────

function ShopForm({
  institutionId,
  initial,
  onDone,
}: {
  institutionId: string;
  initial?: Shop;
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(initial?.name ?? "");
  const [location, setLocation] = useState(initial?.location ?? "");
  const [payOnPickup, setPayOnPickup] = useState(initial?.pay_on_pickup_enabled ?? true);

  const isEdit = !!initial;

  const mutation = useMutation({
    mutationFn: () => {
      if (!name.trim()) throw new Error("Shop name is required.");
      if (isEdit) {
        return updateShop(initial!.id, {
          name: name.trim(),
          location: location.trim() || null,
          pay_on_pickup_enabled: payOnPickup,
        });
      }
      return createShop({
        institution_id: institutionId,
        name: name.trim(),
        location: location.trim() || null,
        pay_on_pickup_enabled: payOnPickup,
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "shops", institutionId] });
      onDone();
    },
  });

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }}
      className="space-y-3"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          label="Shop name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <TextField
          label="Location / room (optional)"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="e.g. Main Library, Room 2"
        />
      </div>
      <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
        <input
          type="checkbox"
          checked={payOnPickup}
          onChange={(e) => setPayOnPickup(e.target.checked)}
          className="h-4 w-4 rounded border border-line"
        />
        <span>Accept pay-on-pickup orders</span>
      </label>
      {mutation.isError && <Alert variant="error">{toUserMessage(mutation.error)}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : isEdit ? "Save changes" : "Create shop"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

// ─── Pricing rule form ────────────────────────────────────────────────────────

function AddRuleForm({ shopId, onDone }: { shopId: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [kind, setKind] = useState<"PER_PAGE" | "PER_COPY" | "PER_ORDER">("PER_PAGE");
  const [paperSize, setPaperSize] = useState("A4");
  const [colorMode, setColorMode] = useState<"BW" | "COLOR">("BW");
  const [duplex, setDuplex] = useState(false);
  const [optionKey, setOptionKey] = useState("");
  const [amount, setAmount] = useState("");

  const mutation = useMutation({
    mutationFn: () => {
      const amountNum = parseInt(amount, 10);
      if (isNaN(amountNum) || amountNum < 0) throw new Error("Amount must be a positive number.");
      if (kind === "PER_PAGE") {
        return addPricingRule(shopId, { kind, paper_size: paperSize, color_mode: colorMode, duplex, amount_ugx: amountNum });
      }
      if (!optionKey.trim()) throw new Error("Option key is required for PER_COPY / PER_ORDER rules.");
      return addPricingRule(shopId, { kind, option_key: optionKey.trim(), amount_ugx: amountNum });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "pricing", shopId] });
      onDone();
    },
  });

  return (
    <form onSubmit={(e) => { e.preventDefault(); mutation.mutate(); }} className="space-y-3 p-4 border border-line rounded-control">
      <h4 className="font-semibold text-sm">Add pricing rule</h4>
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectField label="Rule type" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          <option value="PER_PAGE">Per page</option>
          <option value="PER_COPY">Per copy (option)</option>
          <option value="PER_ORDER">Per order (option)</option>
        </SelectField>
        <TextField label="Amount (UGX)" type="number" value={amount} onChange={(e) => setAmount(e.target.value)} required min={0} />
      </div>
      {kind === "PER_PAGE" && (
        <div className="grid gap-3 sm:grid-cols-3">
          <SelectField label="Paper size" value={paperSize} onChange={(e) => setPaperSize(e.target.value)}>
            {["A4", "A3", "A5", "LETTER"].map((s) => <option key={s} value={s}>{s}</option>)}
          </SelectField>
          <SelectField label="Color" value={colorMode} onChange={(e) => setColorMode(e.target.value as "BW" | "COLOR")}>
            <option value="BW">Black &amp; white</option>
            <option value="COLOR">Color</option>
          </SelectField>
          <label className="flex items-center gap-2 text-sm cursor-pointer self-end pb-2">
            <input type="checkbox" checked={duplex} onChange={(e) => setDuplex(e.target.checked)} className="h-4 w-4" />
            <span>Duplex (double-sided)</span>
          </label>
        </div>
      )}
      {kind !== "PER_PAGE" && (
        <TextField
          label="Option key (e.g. staple, binding)"
          value={optionKey}
          onChange={(e) => setOptionKey(e.target.value)}
          hint="Lowercase letters, digits and underscores only"
          required
        />
      )}
      {mutation.isError && <Alert variant="error">{toUserMessage(mutation.error)}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" size="md" disabled={mutation.isPending}>
          {mutation.isPending ? "Adding…" : "Add rule"}
        </Button>
        <Button type="button" size="md" variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

// ─── Pricing rules table ──────────────────────────────────────────────────────

function PricingRulesTable({ shopId }: { shopId: string }) {
  const qc = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);

  const q = useQuery({
    queryKey: ["admin", "pricing", shopId],
    queryFn: ({ signal }) => listPricingRules(shopId, signal),
  });

  const toggle = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updatePricingRule(shopId, id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "pricing", shopId] }),
  });

  if (q.isPending) return <p className="text-sm text-fg-muted">Loading rules…</p>;
  if (q.isError) return <Alert variant="error">{toUserMessage(q.error)}</Alert>;

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-control border border-line">
        <table className="min-w-full text-xs">
          <thead className="bg-surface">
            <tr>
              {["Type", "Paper", "Color", "Duplex", "Option", "Amount (UGX)", "Active", ""].map((h) => (
                <th key={h} className="px-2 py-2 text-left font-semibold text-fg-muted whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {q.data.length === 0 && (
              <tr><td colSpan={8} className="px-2 py-4 text-center text-fg-muted">No pricing rules yet.</td></tr>
            )}
            {q.data.map((rule) => (
              <tr key={rule.id} className={rule.is_active ? "" : "opacity-50"}>
                <td className="px-2 py-1.5 font-mono">{rule.kind}</td>
                <td className="px-2 py-1.5">{rule.paper_size ?? "—"}</td>
                <td className="px-2 py-1.5">{rule.color_mode ?? "—"}</td>
                <td className="px-2 py-1.5">{rule.duplex != null ? (rule.duplex ? "Yes" : "No") : "—"}</td>
                <td className="px-2 py-1.5 font-mono">{rule.option_key ?? "—"}</td>
                <td className="px-2 py-1.5 font-semibold">{formatUgx(rule.amount_ugx)}</td>
                <td className="px-2 py-1.5">
                  <span className={`rounded-full px-1.5 py-0.5 text-xs font-semibold ${rule.is_active ? "bg-accent/10 text-accent" : "bg-surface text-fg-muted"}`}>
                    {rule.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-2 py-1.5">
                  <button
                    onClick={() => toggle.mutate({ id: rule.id, is_active: !rule.is_active })}
                    className="text-xs text-secondary hover:underline"
                  >
                    {rule.is_active ? "Deactivate" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {showAddForm ? (
        <AddRuleForm shopId={shopId} onDone={() => setShowAddForm(false)} />
      ) : (
        <Button size="md" variant="secondary" onClick={() => setShowAddForm(true)}>+ Add pricing rule</Button>
      )}
    </div>
  );
}

// ─── Shop detail / orders ─────────────────────────────────────────────────────

function ShopOrdersTable({ shopId }: { shopId: string }) {
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ["admin", "shop-orders", shopId, page],
    queryFn: ({ signal }) => listAllOrders({ page, shop_id: shopId }, signal),
    placeholderData: keepPreviousData,
  });

  if (q.isPending) return <p className="text-sm text-fg-muted">Loading orders…</p>;
  if (q.isError) return <Alert variant="error">{toUserMessage(q.error)}</Alert>;

  return (
    <div className="space-y-2">
      <p className="text-xs text-fg-muted">{q.data.meta.total} order{q.data.meta.total !== 1 ? "s" : ""}</p>
      {q.data.items.length === 0 ? (
        <p className="text-sm text-fg-muted">No orders for this shop.</p>
      ) : (
        <div className="overflow-x-auto rounded-control border border-line">
          <table className="min-w-full text-xs">
            <thead className="bg-surface">
              <tr>
                {["Status", "Student", "Total", "Date"].map((h) => (
                  <th key={h} className="px-2 py-2 text-left font-semibold text-fg-muted whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {q.data.items.map((o) => (
                <tr key={o.id}>
                  <td className="px-2 py-1.5"><OrderStatusBadge status={o.status} /></td>
                  <td className="px-2 py-1.5">{o.student_name ?? "—"}</td>
                  <td className="px-2 py-1.5 font-semibold">{formatUgx(o.total_ugx)}</td>
                  <td className="px-2 py-1.5 text-fg-muted">{new Date(o.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {q.data.meta.total > 10 && (
        <div className="flex gap-2 text-sm">
          {page > 1 && <button onClick={() => setPage(p => p - 1)} className="text-secondary hover:underline">← Prev</button>}
          {q.data.items.length === 10 && <button onClick={() => setPage(p => p + 1)} className="text-secondary hover:underline">Next →</button>}
        </div>
      )}
    </div>
  );
}

// ─── Shop row (expandable) ────────────────────────────────────────────────────

function ShopRow({ shop, institutionId }: { shop: Shop; institutionId: string }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [activeSection, setActiveSection] = useState<"orders" | "pricing">("pricing");

  const toggleActive = useMutation({
    mutationFn: () => updateShop(shop.id, { is_active: !shop.is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "shops", institutionId] }),
  });

  return (
    <>
      <tr className={shop.is_active ? "" : "opacity-60"}>
        <td className="px-3 py-2 font-semibold">{shop.name}</td>
        <td className="px-3 py-2 text-fg-muted text-sm">{shop.location ?? <span className="italic">No location set</span>}</td>
        <td className="px-3 py-2">
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${shop.is_active ? "bg-accent/10 text-accent" : "bg-surface text-fg-muted border border-line"}`}>
            {shop.is_active ? "Active" : "Inactive"}
          </span>
        </td>
        <td className="px-3 py-2 text-xs text-fg-muted">{shop.pay_on_pickup_enabled ? "Yes" : "No"}</td>
        <td className="px-3 py-2">
          <div className="flex gap-1 flex-wrap">
            <Button size="md" variant="ghost" onClick={() => { setEditing(true); setExpanded(true); }}>Edit</Button>
            <Button
              size="md"
              variant={shop.is_active ? "secondary" : "ghost"}
              onClick={() => toggleActive.mutate()}
              disabled={toggleActive.isPending}
            >
              {shop.is_active ? "Deactivate" : "Activate"}
            </Button>
            <Button size="md" variant="ghost" onClick={() => { setExpanded(!expanded); setEditing(false); }}>
              {expanded ? "▲ Less" : "▼ Details"}
            </Button>
          </div>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={5} className="px-3 py-4 bg-surface/50">
            {editing ? (
              <div className="space-y-3">
                <h3 className="font-semibold">Edit shop</h3>
                <ShopForm
                  institutionId={institutionId}
                  initial={shop}
                  onDone={() => setEditing(false)}
                />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex gap-2">
                  <button
                    onClick={() => setActiveSection("pricing")}
                    className={`text-sm font-semibold pb-1 border-b-2 ${activeSection === "pricing" ? "border-primary text-primary" : "border-transparent text-fg-muted"}`}
                  >
                    Pricing rules
                  </button>
                  <button
                    onClick={() => setActiveSection("orders")}
                    className={`text-sm font-semibold pb-1 border-b-2 ${activeSection === "orders" ? "border-primary text-primary" : "border-transparent text-fg-muted"}`}
                  >
                    Recent orders
                  </button>
                </div>
                {activeSection === "pricing" && <PricingRulesTable shopId={shop.id} />}
                {activeSection === "orders" && <ShopOrdersTable shopId={shop.id} />}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

// ─── Main PrintShopPanel ──────────────────────────────────────────────────────

export function PrintShopPanel() {
  const [institutionId, setInstitutionId] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [nameFilter, setNameFilter] = useState("");

  const institutions = useQuery({
    queryKey: ["institutions"],
    queryFn: ({ signal }) => listAuthInstitutions(signal),
    staleTime: 300_000,
  });

  const shops = useQuery({
    queryKey: ["admin", "shops", institutionId],
    queryFn: ({ signal }) => listShopsAdmin(institutionId, signal),
    enabled: !!institutionId,
  });

  const filteredShops = shops.data?.filter((s) =>
    !nameFilter || s.name.toLowerCase().includes(nameFilter.toLowerCase())
  ) ?? [];

  return (
    <div className="space-y-6">
      <div className="max-w-xs">
        <SelectField
          label="University"
          value={institutionId}
          onChange={(e) => { setInstitutionId(e.target.value); setShowCreateForm(false); }}
        >
          <option value="">Choose university</option>
          {institutions.data?.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </SelectField>
      </div>

      {!institutionId && (
        <p className="text-fg-muted">Choose a university to manage its print shops.</p>
      )}

      {institutionId && (
        <>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 max-w-xs">
              <TextField
                label="Search shops"
                value={nameFilter}
                onChange={(e) => setNameFilter(e.target.value)}
                placeholder="Filter by name…"
              />
            </div>
            {!showCreateForm && (
              <Button onClick={() => setShowCreateForm(true)} className="self-end">
                + New shop
              </Button>
            )}
          </div>

          {showCreateForm && (
            <Card className="space-y-4">
              <h3 className="font-bold">Create print shop</h3>
              <ShopForm
                institutionId={institutionId}
                onDone={() => setShowCreateForm(false)}
              />
            </Card>
          )}

          {shops.isPending && <p role="status" className="text-fg-muted">Loading shops…</p>}
          {shops.isError && <Alert variant="error">{toUserMessage(shops.error)}</Alert>}

          {shops.data && (
            <div className="overflow-x-auto rounded-card border border-line">
              <table className="min-w-full text-sm">
                <thead className="bg-surface">
                  <tr>
                    {["Shop name", "Location", "Status", "Pay-on-pickup", "Actions"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {filteredShops.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-3 py-6 text-center text-fg-muted">
                        {nameFilter ? "No shops match that name." : "No print shops for this institution yet."}
                      </td>
                    </tr>
                  )}
                  {filteredShops.map((shop) => (
                    <ShopRow key={shop.id} shop={shop} institutionId={institutionId} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
