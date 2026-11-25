import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TextField, SelectField } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { useAuth } from "@/features/auth/auth-context";
import {
  changeAdStatus,
  createAdvertiser,
  createAd,
  createCampaign,
  createInstitution,
  getAdMetrics,
  getAnalytics,
  grantRole,
  listAdminUsers,
  listAds,
  listAdvertisers,
  listAllOrders,
  listAuditLogs,
  listCampaigns,
  reinstateUser,
  revokeRole,
  suspendUser,
  triggerOutboxProcess,
  updateCampaign,
  updateInstitution,
} from "@/features/admin/api";
import { listInstitutions as listAuthInstitutions } from "@/features/auth/api";
import { PrintShopPanel } from "@/features/admin/PrintShopPanel";
import { AcademicManagementPanel } from "@/features/admin/AcademicManagementPanel";
import { OrderStatusBadge, PaymentStatusBadge } from "@/features/printing/OrderBadges";
import { toUserMessage } from "@/lib/api/errors";
import { formatUgx } from "@/lib/format";

// ─── Analytics Overview ───────────────────────────────────────────────────────

function OverviewPanel() {
  const q = useQuery({ queryKey: ["admin", "analytics"], queryFn: ({ signal }) => getAnalytics(signal) });
  if (q.isPending) return <p role="status" className="text-fg-muted">Loading metrics…</p>;
  if (q.isError) return <Alert variant="error">{toUserMessage(q.error)}</Alert>;
  const d = q.data;
  const stats = [
    { label: "Users", value: d.total_users, color: "text-primary" },
    { label: "Resources", value: d.total_resources, color: "text-fg" },
    { label: "Published", value: d.published_resources, color: "text-accent" },
    { label: "Print orders", value: d.total_orders, color: "text-fg" },
    { label: "Completed orders", value: d.completed_orders, color: "text-accent" },
    { label: "Ad impressions", value: d.total_impressions, color: "text-secondary" },
    { label: "Ad clicks", value: d.total_clicks, color: "text-secondary" },
  ];
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label} className="text-center space-y-1 py-5">
            <p className={`text-3xl font-extrabold ${s.color}`}>{s.value.toLocaleString()}</p>
            <p className="text-sm text-fg-muted">{s.label}</p>
          </Card>
        ))}
      </div>
      <Card className="space-y-3">
        <h2 className="text-lg font-bold">Quick access</h2>
        <div className="flex flex-wrap gap-2">
          <Link to="/moderation" className="rounded-control border border-line px-4 py-2 text-sm font-semibold hover:bg-surface">
            Resource moderation →
          </Link>
        </div>
      </Card>
    </div>
  );
}

// ─── User Management ──────────────────────────────────────────────────────────

function RoleManager({ userId, currentRoles }: { userId: string; currentRoles: string[] }) {
  const qc = useQueryClient();
  const [role, setRole] = useState("STUDENT");
  const [expanded, setExpanded] = useState(false);

  const grant = useMutation({
    mutationFn: () => grantRole(userId, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
  const revoke = useMutation({
    mutationFn: (r: string) => revokeRole(userId, r),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  if (!expanded) {
    return (
      <Button variant="ghost" size="md" onClick={() => setExpanded(true)}>
        Manage roles
      </Button>
    );
  }

  return (
    <div className="space-y-2 rounded-control border border-line p-3">
      <p className="text-xs font-semibold text-fg-muted">Current roles: {currentRoles.join(", ") || "none"}</p>
      <div className="flex gap-2 flex-wrap">
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="min-h-10 rounded-control border border-line bg-raised px-2 text-sm"
        >
          {["STUDENT", "RESOURCE_PROVIDER", "PRINTING_OPERATOR", "ADMIN"].map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <Button size="md" variant="secondary" onClick={() => grant.mutate()} disabled={grant.isPending}>
          Grant
        </Button>
        <Button size="md" variant="ghost" onClick={() => setExpanded(false)}>
          Done
        </Button>
      </div>
      {currentRoles.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {currentRoles.map((r) => (
            <button
              key={r}
              onClick={() => revoke.mutate(r)}
              disabled={revoke.isPending}
              className="rounded-full border border-line px-2 py-0.5 text-xs hover:bg-danger/10 hover:text-danger-strong"
            >
              {r} ✕
            </button>
          ))}
        </div>
      )}
      {(grant.isError || revoke.isError) && (
        <Alert variant="error">{toUserMessage(grant.error ?? revoke.error)}</Alert>
      )}
    </div>
  );
}

function UserManagement() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [draftSearch, setDraftSearch] = useState("");
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ["admin", "users", page, search],
    queryFn: ({ signal }) => listAdminUsers({ page, q: search || undefined }, signal),
    placeholderData: keepPreviousData,
  });

  const suspend = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => suspendUser(id, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
  const reinstate = useMutation({
    mutationFn: (id: string) => reinstateUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => { e.preventDefault(); setSearch(draftSearch); setPage(1); }}
        className="flex gap-2"
      >
        <div className="flex-1">
          <TextField
            label="Search users"
            type="search"
            value={draftSearch}
            onChange={(e) => setDraftSearch(e.target.value)}
            placeholder="Name or email"
          />
        </div>
        <Button type="submit" className="self-end min-h-11">Search</Button>
      </form>

      {q.isPending && <p role="status" className="text-fg-muted">Loading…</p>}
      {q.isError && <Alert variant="error">{toUserMessage(q.error)}</Alert>}

      {q.data && (
        <>
          <div className="overflow-x-auto rounded-card border border-line">
            <table className="min-w-full text-sm">
              <thead className="bg-surface">
                <tr>
                  {["Name", "Email", "Status", "Roles", "Joined", "Actions"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {q.data.items.length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-6 text-center text-fg-muted">No users found.</td></tr>
                )}
                {q.data.items.map((user) => (
                  <tr key={user.id}>
                    <td className="px-3 py-2 font-semibold whitespace-nowrap">{user.full_name}</td>
                    <td className="px-3 py-2 text-fg-muted break-all">{user.email}</td>
                    <td className="px-3 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        user.status === "ACTIVE" ? "bg-accent/10 text-accent" : "bg-danger/10 text-danger-strong"
                      }`}>
                        {user.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-fg-muted text-xs">{user.roles.join(", ") || "—"}</td>
                    <td className="px-3 py-2 text-fg-muted whitespace-nowrap">
                      {new Date(user.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-col gap-1">
                        {user.status === "ACTIVE" ? (
                          <Button
                            variant="secondary" size="md"
                            onClick={() => {
                              const reason = window.prompt("Suspension reason:");
                              if (reason?.trim()) suspend.mutate({ id: user.id, reason });
                            }}
                          >
                            Suspend
                          </Button>
                        ) : (
                          <Button variant="secondary" size="md" onClick={() => reinstate.mutate(user.id)}>
                            Reinstate
                          </Button>
                        )}
                        <RoleManager userId={user.id} currentRoles={user.roles} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onChange={setPage} />
        </>
      )}
    </div>
  );
}

// ─── Institutions ─────────────────────────────────────────────────────────────

function InstitutionsPanel() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", code: "", slug: "" });

  const q = useQuery({ queryKey: ["admin", "institutions"], queryFn: ({ signal }) => listAuthInstitutions(signal) });

  const create = useMutation({
    mutationFn: () => createInstitution(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin", "institutions"] }); setForm({ name: "", code: "", slug: "" }); },
  });

  const update = useMutation({
    mutationFn: () => updateInstitution(editing!, { name: form.name, code: form.code }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin", "institutions"] }); setEditing(null); },
  });

  function startEdit(inst: { id: string; name: string; code: string; slug: string }) {
    setEditing(inst.id);
    setForm({ name: inst.name, code: inst.code, slug: inst.slug });
  }

  return (
    <div className="space-y-6">
      <Card className="space-y-4">
        <h3 className="font-bold">{editing ? "Edit institution" : "Add institution"}</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <TextField label="Name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
          <TextField label="Code" value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))} hint="e.g. MAK" />
          {!editing && (
            <TextField label="Slug" value={form.slug} onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))} hint="e.g. makerere" />
          )}
        </div>
        {(create.isError || update.isError) && (
          <Alert variant="error">{toUserMessage(create.error ?? update.error)}</Alert>
        )}
        <div className="flex gap-2">
          <Button
            disabled={(create.isPending || update.isPending) || !form.name.trim()}
            onClick={() => editing ? update.mutate() : create.mutate()}
          >
            {editing ? "Save changes" : "Create institution"}
          </Button>
          {editing && <Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>}
        </div>
      </Card>

      {q.isPending && <p role="status" className="text-fg-muted">Loading…</p>}
      {q.isError && <Alert variant="error">{toUserMessage(q.error)}</Alert>}
      {q.data && (
        <div className="overflow-x-auto rounded-card border border-line">
          <table className="min-w-full text-sm">
            <thead className="bg-surface">
              <tr>
                {["Name", "Code", "Slug", "Actions"].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {q.data.map((inst) => (
                <tr key={inst.id}>
                  <td className="px-3 py-2 font-semibold">{inst.name}</td>
                  <td className="px-3 py-2 text-fg-muted">{inst.code}</td>
                  <td className="px-3 py-2 text-fg-muted">{inst.slug}</td>
                  <td className="px-3 py-2">
                    <Button variant="ghost" size="md" onClick={() => startEdit(inst)}>Edit</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Academic management ──────────────────────────────────────────────────────

function AcademicPanel() {
  return <AcademicManagementPanel />;
}

// ─── Printing Management ──────────────────────────────────────────────────────

// ─── Printing Management ──────────────────────────────────────────────────────

function PrintingPanel() {
  const [printingTab, setPrintingTab] = useState<"orders" | "shops">("orders");
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");

  const q = useQuery({
    queryKey: ["admin", "printing", page, status],
    queryFn: ({ signal }) => listAllOrders({ page, status: status || undefined }, signal),
    enabled: printingTab === "orders",
    placeholderData: keepPreviousData,
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b border-line pb-2">
        {(["orders", "shops"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setPrintingTab(t)}
            className={`rounded-control px-4 py-1.5 text-sm font-semibold transition-colors ${printingTab === t ? "bg-primary text-white" : "text-fg-muted hover:bg-surface"}`}
          >
            {t === "orders" ? "All orders" : "Shop management"}
          </button>
        ))}
      </div>

      {printingTab === "shops" && <PrintShopPanel />}

      {printingTab === "orders" && (
        <>
          <div className="max-w-xs">
            <SelectField label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              <option value="">All open orders</option>
              <option value="SUBMITTED">Submitted</option>
              <option value="ACCEPTED">Accepted</option>
              <option value="PRINTING">Printing</option>
              <option value="READY_FOR_PICKUP">Ready for pickup</option>
              <option value="COMPLETED">Completed</option>
              <option value="REJECTED">Rejected</option>
              <option value="CANCELLED">Cancelled</option>
            </SelectField>
          </div>

          {q.isPending && <p role="status" className="text-fg-muted">Loading orders…</p>}
          {q.isError && <Alert variant="error">{toUserMessage(q.error)}</Alert>}

          {q.data && (
            <>
              <p className="text-sm text-fg-muted" role="status">{q.data.meta.total} orders</p>
              <div className="overflow-x-auto rounded-card border border-line">
                <table className="min-w-full text-sm">
                  <thead className="bg-surface">
                    <tr>
                      {["Status", "Payment", "Shop", "Student", "Total", "Date", "Actions"].map((h) => (
                        <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {q.data.items.length === 0 && (
                      <tr><td colSpan={7} className="px-3 py-6 text-center text-fg-muted">No orders found.</td></tr>
                    )}
                    {q.data.items.map((order) => (
                      <tr key={order.id}>
                        <td className="px-3 py-2"><OrderStatusBadge status={order.status} /></td>
                        <td className="px-3 py-2"><PaymentStatusBadge status={order.payment_status} method={order.payment_method} /></td>
                        <td className="px-3 py-2 whitespace-nowrap">{order.shop_name}</td>
                        <td className="px-3 py-2 whitespace-nowrap">{order.student_name ?? "—"}</td>
                        <td className="px-3 py-2 whitespace-nowrap font-semibold">{formatUgx(order.total_ugx)}</td>
                        <td className="px-3 py-2 text-fg-muted whitespace-nowrap">{new Date(order.created_at).toLocaleDateString()}</td>
                        <td className="px-3 py-2">
                          <Link to={`/operator/orders/${order.id}`} className="text-sm text-brand underline whitespace-nowrap">
                            View →
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={page} pageSize={20} total={q.data.meta.total} onChange={setPage} />
            </>
          )}
        </>
      )}
    </div>
  );
}

// ─── Resource Moderation ──────────────────────────────────────────────────────

function ModerationPanel() {
  return (
    <div className="space-y-4">
      <p className="text-fg-muted">
        Resources submitted by providers are reviewed here before they go live.
      </p>
      <Link
        to="/moderation"
        className="inline-flex items-center gap-2 rounded-control bg-primary px-5 py-2.5 text-sm font-semibold text-white hover:bg-primary-hover"
      >
        Open moderation queue →
      </Link>
    </div>
  );
}

// ─── Notifications admin ──────────────────────────────────────────────────────

function NotificationsAdminPanel() {
  const qc = useQueryClient();
  const process = useMutation({
    mutationFn: () => triggerOutboxProcess(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin"] }),
  });

  return (
    <div className="space-y-6">
      <Alert variant="info">
        Notifications are queued in the outbox and processed by a background job. Use the button below to trigger processing immediately in development or if the job is delayed.
      </Alert>
      <Card className="space-y-3">
        <h3 className="font-bold">Outbox processing</h3>
        <p className="text-sm text-fg-muted">
          Processes all pending notification outbox entries, delivering them to their recipients.
        </p>
        <Button onClick={() => process.mutate()} disabled={process.isPending}>
          {process.isPending ? "Processing…" : "Process notification outbox"}
        </Button>
        {process.isSuccess && (
          <Alert variant="success">{(process.data as { message: string }).message}</Alert>
        )}
        {process.isError && <Alert variant="error">{toUserMessage(process.error)}</Alert>}
      </Card>
    </div>
  );
}

// ─── Audit Log ────────────────────────────────────────────────────────────────

function AuditLogPanel() {
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");
  const [draftAction, setDraftAction] = useState("");

  const q = useQuery({
    queryKey: ["admin", "audit", page, actionFilter],
    queryFn: ({ signal }) => listAuditLogs({ page, action: actionFilter || undefined }, signal),
    placeholderData: keepPreviousData,
  });

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); setActionFilter(draftAction); setPage(1); }} className="flex gap-2">
        <div className="flex-1">
          <TextField label="Filter by action" type="search" value={draftAction} onChange={(e) => setDraftAction(e.target.value)} placeholder="e.g. user.suspended" />
        </div>
        <Button type="submit" className="self-end min-h-11">Filter</Button>
      </form>

      {q.isPending && <p role="status" className="text-fg-muted">Loading…</p>}
      {q.isError && <Alert variant="error">{toUserMessage(q.error)}</Alert>}

      {q.data && (
        <>
          <div className="overflow-x-auto rounded-card border border-line">
            <table className="min-w-full text-sm">
              <thead className="bg-surface">
                <tr>
                  {["Time", "Action", "Outcome", "Target", "IP"].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {q.data.items.length === 0 && (
                  <tr><td colSpan={5} className="px-3 py-6 text-center text-fg-muted">No log entries found.</td></tr>
                )}
                {q.data.items.map((log) => (
                  <tr key={log.id}>
                    <td className="px-3 py-2 text-fg-muted whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{log.action}</td>
                    <td className="px-3 py-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        log.outcome === "SUCCESS" ? "bg-accent/10 text-accent" :
                        log.outcome === "FAILURE" ? "bg-danger/10 text-danger-strong" :
                        "bg-warning/10 text-warning"
                      }`}>
                        {log.outcome}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-fg-muted text-xs">
                      {log.target_type && `${log.target_type}: ${log.target_id?.slice(0, 8)}…`}
                    </td>
                    <td className="px-3 py-2 text-fg-muted text-xs">{log.ip_address ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={q.data.page_size} total={q.data.total} onChange={setPage} />
        </>
      )}
    </div>
  );
}

// ─── Advertising ─────────────────────────────────────────────────────────────

function AdStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ACTIVE: "bg-accent/10 text-accent",
    DRAFT: "bg-surface text-fg-muted",
    SCHEDULED: "bg-secondary/10 text-secondary",
    PAUSED: "bg-warning/10 text-warning",
    REJECTED: "bg-danger/10 text-danger-strong",
    ARCHIVED: "bg-surface text-fg-muted",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${colors[status] ?? "bg-surface text-fg-muted"}`}>
      {status}
    </span>
  );
}

function AdMetricsCell({ adId }: { adId: string }) {
  const q = useQuery({
    queryKey: ["admin", "ads", "metrics", adId],
    queryFn: ({ signal }) => getAdMetrics(adId, signal),
  });
  if (q.isPending) return <span className="text-fg-muted">…</span>;
  if (q.isError) return <span className="text-fg-muted">—</span>;
  return <span>{q.data.impressions.toLocaleString()} imp / {q.data.clicks.toLocaleString()} clk</span>;
}

function CreateCampaignForm({ advertisers }: { advertisers: { id: string; name: string }[] }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ advertiser_id: "", name: "", starts_at: "", ends_at: "" });

  const create = useMutation({
    mutationFn: () => createCampaign({
      advertiser_id: form.advertiser_id,
      name: form.name,
      starts_at: form.starts_at || null,
      ends_at: form.ends_at || null,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin", "campaigns"] }); setForm({ advertiser_id: "", name: "", starts_at: "", ends_at: "" }); },
  });

  return (
    <details className="rounded-control border border-line">
      <summary className="cursor-pointer px-4 py-3 font-semibold select-none">+ New campaign</summary>
      <div className="border-t border-line p-4 space-y-3">
        <SelectField label="Advertiser" value={form.advertiser_id} onChange={(e) => setForm((f) => ({ ...f, advertiser_id: e.target.value }))}>
          <option value="">Choose advertiser</option>
          {advertisers.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </SelectField>
        <TextField label="Campaign name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField label="Start date (optional)" type="date" value={form.starts_at} onChange={(e) => setForm((f) => ({ ...f, starts_at: e.target.value }))} />
          <TextField label="End date (optional)" type="date" value={form.ends_at} onChange={(e) => setForm((f) => ({ ...f, ends_at: e.target.value }))} />
        </div>
        {create.isError && <Alert variant="error">{toUserMessage(create.error)}</Alert>}
        <Button disabled={!form.advertiser_id || !form.name || create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? "Creating…" : "Create campaign"}
        </Button>
      </div>
    </details>
  );
}

function EditCampaignForm({
  campaign,
  onDone,
}: {
  campaign: { id: string; name: string; starts_at: string | null; ends_at: string | null; is_active: boolean };
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(campaign.name);
  const [startsAt, setStartsAt] = useState(campaign.starts_at ? campaign.starts_at.slice(0, 10) : "");
  const [endsAt, setEndsAt] = useState(campaign.ends_at ? campaign.ends_at.slice(0, 10) : "");

  const update = useMutation({
    mutationFn: () => updateCampaign(campaign.id, {
      name: name.trim() || undefined,
      starts_at: startsAt || null,
      ends_at: endsAt || null,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin", "campaigns"] }); onDone(); },
  });

  const toggleActive = useMutation({
    mutationFn: () => updateCampaign(campaign.id, { is_active: !campaign.is_active }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin", "campaigns"] }); onDone(); },
  });

  return (
    <div className="p-4 space-y-3 border border-line rounded-control bg-surface">
      <h4 className="font-semibold text-sm">Edit campaign</h4>
      <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} required />
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label="Start date" type="date" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} />
        <TextField label="End date" type="date" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} />
      </div>
      {update.isError && <Alert variant="error">{toUserMessage(update.error)}</Alert>}
      <div className="flex gap-2 flex-wrap">
        <Button size="md" disabled={update.isPending} onClick={() => update.mutate()}>Save changes</Button>
        <Button
          size="md"
          variant="secondary"
          disabled={toggleActive.isPending}
          onClick={() => toggleActive.mutate()}
        >
          {campaign.is_active ? "Deactivate" : "Activate"} campaign
        </Button>
        <Button size="md" variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </div>
  );
}

function CreateAdForm({ campaigns }: { campaigns: { id: string; name: string }[] }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ campaign_id: "", title: "", body: "", click_url: "", placement: "dashboard_banner", starts_at: "", ends_at: "" });

  const create = useMutation({
    mutationFn: () => createAd({
      campaign_id: form.campaign_id,
      title: form.title,
      body: form.body || null,
      click_url: form.click_url || null,
      placement: form.placement,
      starts_at: form.starts_at || null,
      ends_at: form.ends_at || null,
      target_institution_ids: [],
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin", "ads"] }); setForm((f) => ({ ...f, title: "", body: "", click_url: "" })); },
  });

  return (
    <details className="rounded-control border border-line">
      <summary className="cursor-pointer px-4 py-3 font-semibold select-none">+ New advertisement</summary>
      <div className="border-t border-line p-4 space-y-3">
        <SelectField label="Campaign" value={form.campaign_id} onChange={(e) => setForm((f) => ({ ...f, campaign_id: e.target.value }))}>
          <option value="">Choose campaign</option>
          {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </SelectField>
        <TextField label="Title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
        <div className="space-y-1">
          <label className="block text-sm font-semibold">Body (optional)</label>
          <textarea value={form.body} onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))} className="w-full min-h-20 rounded-control border border-line bg-raised p-3 text-sm" />
        </div>
        <TextField label="Click URL (optional)" type="url" value={form.click_url} onChange={(e) => setForm((f) => ({ ...f, click_url: e.target.value }))} />
        <SelectField label="Placement" value={form.placement} onChange={(e) => setForm((f) => ({ ...f, placement: e.target.value }))}>
          <option value="dashboard_banner">Dashboard banner</option>
          <option value="operator_dashboard">Operator dashboard</option>
          <option value="resource_browse">Resource browse</option>
          <option value="sidebar">Sidebar</option>
        </SelectField>
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField label="Start date (optional)" type="date" value={form.starts_at} onChange={(e) => setForm((f) => ({ ...f, starts_at: e.target.value }))} />
          <TextField label="End date (optional)" type="date" value={form.ends_at} onChange={(e) => setForm((f) => ({ ...f, ends_at: e.target.value }))} />
        </div>
        {create.isError && <Alert variant="error">{toUserMessage(create.error)}</Alert>}
        <Button disabled={!form.campaign_id || !form.title || create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? "Creating…" : "Create advertisement"}
        </Button>
      </div>
    </details>
  );
}

function AdvertisingPanel() {
  const qc = useQueryClient();
  const [selectedCampaign, setSelectedCampaign] = useState("");
  const [editingCampaign, setEditingCampaign] = useState<string | null>(null);

  const advertisers = useQuery({ queryKey: ["admin", "advertisers"], queryFn: ({ signal }) => listAdvertisers(signal) });
  const campaigns = useQuery({ queryKey: ["admin", "campaigns"], queryFn: ({ signal }) => listCampaigns(undefined, signal) });
  const ads = useQuery({
    queryKey: ["admin", "ads", selectedCampaign],
    queryFn: ({ signal }) => listAds({ campaignId: selectedCampaign || undefined }, signal),
  });

  const changeStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => changeAdStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "ads"] }),
  });

  const newAdvertiser = useMutation({
    mutationFn: ({ name, email }: { name: string; email: string }) =>
      createAdvertiser({ name, contact_email: email }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "advertisers"] }),
  });

  const editingCampaignData = campaigns.data?.find((c) => c.id === editingCampaign);

  return (
    <div className="space-y-6">
      {/* Advertisers */}
      <Card className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-bold">Advertisers ({advertisers.data?.length ?? "…"})</h3>
          <Button
            variant="secondary" size="md"
            onClick={() => {
              const name = window.prompt("Advertiser name:");
              const email = window.prompt("Contact email:");
              if (name && email) newAdvertiser.mutate({ name, email });
            }}
          >
            + New advertiser
          </Button>
        </div>
        {advertisers.data && advertisers.data.length > 0 && (
          <ul className="text-sm space-y-1">
            {advertisers.data.map((a) => (
              <li key={a.id} className="flex gap-2">
                <span className="font-semibold">{a.name}</span>
                <span className="text-fg-muted">{a.contact_email}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Campaign list with edit */}
      {campaigns.data && campaigns.data.length > 0 && (
        <Card className="space-y-3">
          <h3 className="font-bold">Campaigns ({campaigns.data.length})</h3>
          <div className="overflow-x-auto rounded-control border border-line">
            <table className="min-w-full text-sm">
              <thead className="bg-surface">
                <tr>{["Name", "Status", "Start", "End", "Actions"].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted whitespace-nowrap">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-line">
                {campaigns.data.map((c) => (
                  <>
                    <tr key={c.id}>
                      <td className="px-3 py-2 font-semibold">{c.name}</td>
                      <td className="px-3 py-2">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${c.is_active ? "bg-accent/10 text-accent" : "bg-surface text-fg-muted border border-line"}`}>
                          {c.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-fg-muted text-xs">{c.starts_at ? new Date(c.starts_at).toLocaleDateString() : "—"}</td>
                      <td className="px-3 py-2 text-fg-muted text-xs">{c.ends_at ? new Date(c.ends_at).toLocaleDateString() : "—"}</td>
                      <td className="px-3 py-2">
                        <Button size="md" variant="ghost" onClick={() => setEditingCampaign(editingCampaign === c.id ? null : c.id)}>
                          {editingCampaign === c.id ? "Cancel" : "Edit"}
                        </Button>
                      </td>
                    </tr>
                    {editingCampaign === c.id && editingCampaignData && (
                      <tr>
                        <td colSpan={5} className="px-3 py-3 bg-surface/50">
                          <EditCampaignForm campaign={editingCampaignData} onDone={() => setEditingCampaign(null)} />
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Create forms */}
      <div className="space-y-3">
        <CreateCampaignForm advertisers={advertisers.data ?? []} />
        <CreateAdForm campaigns={campaigns.data ?? []} />
      </div>

      {/* Campaign filter */}
      <div className="max-w-xs">
        <SelectField label="Filter ads by campaign" value={selectedCampaign} onChange={(e) => setSelectedCampaign(e.target.value)}>
          <option value="">All campaigns</option>
          {campaigns.data?.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </SelectField>
      </div>

      {/* Ads table */}
      {ads.isPending && <p role="status" className="text-fg-muted">Loading ads…</p>}
      {ads.isError && <Alert variant="error">{toUserMessage(ads.error)}</Alert>}
      {ads.data && (
        <div className="overflow-x-auto rounded-card border border-line">
          <table className="min-w-full text-sm">
            <thead className="bg-surface">
              <tr>
                {["Title", "Status", "Placement", "Schedule", "Metrics", "Actions"].map((h) => (
                  <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {ads.data.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-6 text-center text-fg-muted">No advertisements found.</td></tr>
              )}
              {ads.data.map((ad) => (
                <tr key={ad.id}>
                  <td className="px-3 py-2 font-semibold">{ad.title}</td>
                  <td className="px-3 py-2"><AdStatusBadge status={ad.status} /></td>
                  <td className="px-3 py-2 text-fg-muted text-xs">{ad.placement}</td>
                  <td className="px-3 py-2 text-fg-muted text-xs">
                    {ad.starts_at ? new Date(ad.starts_at).toLocaleDateString() : "—"} –{" "}
                    {ad.ends_at ? new Date(ad.ends_at).toLocaleDateString() : "∞"}
                  </td>
                  <td className="px-3 py-2 text-xs"><AdMetricsCell adId={ad.id} /></td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1 flex-wrap">
                      {ad.status === "DRAFT" && (
                        <Button variant="secondary" size="md" onClick={() => changeStatus.mutate({ id: ad.id, status: "ACTIVE" })}>
                          Activate
                        </Button>
                      )}
                      {ad.status === "ACTIVE" && (
                        <Button variant="secondary" size="md" onClick={() => changeStatus.mutate({ id: ad.id, status: "PAUSED" })}>
                          Pause
                        </Button>
                      )}
                      {ad.status === "PAUSED" && (
                        <Button variant="secondary" size="md" onClick={() => changeStatus.mutate({ id: ad.id, status: "ACTIVE" })}>
                          Resume
                        </Button>
                      )}
                      {ad.status !== "ARCHIVED" && (
                        <Button variant="ghost" size="md" onClick={() => changeStatus.mutate({ id: ad.id, status: "ARCHIVED" })}>
                          Archive
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Main Admin Page ──────────────────────────────────────────────────────────

type Tab = "overview" | "users" | "institutions" | "academic" | "moderation" | "printing" | "notifications" | "audit" | "advertising";

const VALID_TABS: Tab[] = ["overview", "users", "institutions", "academic", "moderation", "printing", "notifications", "audit", "advertising"];

export function AdminPage() {
  const { canAny } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // Read tab from URL ?tab=... so the AdminDashboard deep-links work.
  const urlTab = searchParams.get("tab") as Tab | null;
  const [tab, setTab] = useState<Tab>(
    urlTab && VALID_TABS.includes(urlTab) ? urlTab : "overview",
  );

  // Keep URL in sync when tab changes programmatically.
  useEffect(() => {
    const current = searchParams.get("tab");
    if (current !== tab) {
      const next = new URLSearchParams(searchParams);
      next.set("tab", tab);
      setSearchParams(next, { replace: true });
    }
  }, [tab, searchParams, setSearchParams]);

  // Reflect URL changes (e.g. browser back/forward or deep links from AdminDashboard).
  useEffect(() => {
    const incoming = searchParams.get("tab") as Tab | null;
    if (incoming && VALID_TABS.includes(incoming) && incoming !== tab) {
      setTab(incoming);
    }
  }, [searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  const tabs: { id: Tab; label: string; visible: boolean }[] = [
    { id: "overview",      label: "Overview",        visible: true },
    { id: "users",         label: "Users",           visible: canAny("user:read") },
    { id: "institutions",  label: "Institutions",    visible: canAny("institution:manage") || canAny("institution:update") },
    { id: "academic",      label: "Academic",        visible: canAny("catalog:manage") || canAny("user:read") },
    { id: "moderation",    label: "Moderation",      visible: canAny("resource:review") },
    { id: "printing",      label: "Printing",        visible: canAny("order:read_any") || canAny("user:read") },
    { id: "notifications", label: "Notifications",   visible: canAny("analytics:read") },
    { id: "audit",         label: "Audit log",       visible: canAny("audit:read") },
    { id: "advertising",   label: "Advertising",     visible: canAny("advertisement:manage") },
  ];

  const visibleTabs = tabs.filter((t) => t.visible);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">Admin</h1>

      {/* Tab navigation */}
      <div
        role="tablist"
        aria-label="Admin sections"
        className="flex flex-wrap gap-1 border-b border-line pb-2 -mb-px"
      >
        {visibleTabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-t-control px-4 py-2 text-sm font-semibold transition-colors ${
              tab === t.id
                ? "bg-primary text-white"
                : "text-fg-muted hover:bg-surface hover:text-fg"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === "overview"      && <OverviewPanel />}
        {tab === "users"         && <UserManagement />}
        {tab === "institutions"  && <InstitutionsPanel />}
        {tab === "academic"      && <AcademicPanel />}
        {tab === "moderation"    && <ModerationPanel />}
        {tab === "printing"      && <PrintingPanel />}
        {tab === "notifications" && <NotificationsAdminPanel />}
        {tab === "audit"         && <AuditLogPanel />}
        {tab === "advertising"   && <AdvertisingPanel />}
      </div>
    </div>
  );
}
