import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TextField, SelectField } from "@/components/ui/Field";
import { Pagination } from "@/components/ui/Pagination";
import { useAuth } from "@/features/auth/auth-context";
import {
  changeAdStatus,
  createAdvertiser,
  getAdMetrics,
  getAnalytics,
  listAdminUsers,
  listAds,
  listAdvertisers,
  listAuditLogs,
  listCampaigns,
  reinstateUser,
  suspendUser,
} from "@/features/admin/api";
import { toUserMessage } from "@/lib/api/errors";

// ─── Analytics Overview ───────────────────────────────────────────────────────

function OverviewPanel() {
  const q = useQuery({ queryKey: ["admin", "analytics"], queryFn: ({ signal }) => getAnalytics(signal) });
  if (q.isPending) return <p role="status" className="text-fg-muted">Loading metrics…</p>;
  if (q.isError) return <Alert variant="error">{toUserMessage(q.error)}</Alert>;
  const d = q.data;
  const stats = [
    { label: "Users", value: d.total_users },
    { label: "Resources", value: d.total_resources },
    { label: "Published", value: d.published_resources },
    { label: "Orders", value: d.total_orders },
    { label: "Completed orders", value: d.completed_orders },
    { label: "Ad impressions", value: d.total_impressions },
    { label: "Ad clicks", value: d.total_clicks },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {stats.map((s) => (
        <Card key={s.label} className="text-center space-y-1 py-4">
          <p className="text-2xl font-extrabold">{s.value.toLocaleString()}</p>
          <p className="text-sm text-fg-muted">{s.label}</p>
        </Card>
      ))}
    </div>
  );
}

// ─── User Management ──────────────────────────────────────────────────────────

function UserManagement() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const qc = useQueryClient();

  const q = useQuery({
    queryKey: ["admin", "users", page, search],
    queryFn: ({ signal }) => listAdminUsers({ page, q: search || undefined }, signal),
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
        onSubmit={(e) => { e.preventDefault(); setPage(1); }}
        className="flex gap-2"
      >
        <div className="flex-1">
          <TextField
            label="Search users"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
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
                    <th key={h} className="px-3 py-2 text-left font-semibold text-fg-muted">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
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
                    <td className="px-3 py-2 text-fg-muted">{user.roles.join(", ") || "—"}</td>
                    <td className="px-3 py-2 text-fg-muted whitespace-nowrap">
                      {new Date(user.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-3 py-2">
                      {user.status === "ACTIVE" ? (
                        <Button
                          variant="secondary"
                          size="md"
                          onClick={() => {
                            const reason = window.prompt("Suspension reason (required):");
                            if (reason?.trim()) suspend.mutate({ id: user.id, reason });
                          }}
                        >
                          Suspend
                        </Button>
                      ) : (
                        <Button
                          variant="secondary"
                          size="md"
                          onClick={() => reinstate.mutate(user.id)}
                        >
                          Reinstate
                        </Button>
                      )}
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

// ─── Audit Log ────────────────────────────────────────────────────────────────

function AuditLogPanel() {
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");

  const q = useQuery({
    queryKey: ["admin", "audit", page, actionFilter],
    queryFn: ({ signal }) => listAuditLogs({ page, action: actionFilter || undefined }, signal),
  });

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); setPage(1); }} className="flex gap-2">
        <div className="flex-1">
          <TextField label="Filter by action" type="search" value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} placeholder="e.g. user.suspended" />
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
  return <span>{q.data.impressions} imp / {q.data.clicks} clk</span>;
}

function AdvertisingPanel() {
  const qc = useQueryClient();
  const [selectedCampaign, setSelectedCampaign] = useState("");

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

  return (
    <div className="space-y-6">
      {/* Stats */}
      <Card className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-bold">Advertisers ({advertisers.data?.length ?? "…"})</h3>
          <Button
            variant="secondary"
            size="md"
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

      {/* Campaign filter */}
      <div className="flex gap-3 items-end">
        <div className="flex-1 max-w-xs">
          <SelectField label="Filter by campaign" value={selectedCampaign} onChange={(e) => setSelectedCampaign(e.target.value)}>
            <option value="">All campaigns</option>
            {campaigns.data?.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </SelectField>
        </div>
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

type Tab = "overview" | "users" | "audit" | "advertising";

export function AdminPage() {
  const { can } = useAuth();
  const [tab, setTab] = useState<Tab>("overview");

  const tabs: { id: Tab; label: string; visible: boolean }[] = [
    { id: "overview", label: "Overview", visible: true },
    { id: "users", label: "Users", visible: can("user:read") },
    { id: "audit", label: "Audit log", visible: can("audit:read") },
    { id: "advertising", label: "Advertising", visible: can("advertisement:manage") },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-extrabold">Admin</h1>

      <div role="tablist" className="flex flex-wrap gap-1 border-b border-line pb-2">
        {tabs.filter((t) => t.visible).map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-control px-4 py-2 text-sm font-semibold transition-colors ${
              tab === t.id
                ? "bg-primary text-white"
                : "text-fg-muted hover:bg-surface"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {tab === "overview" && <OverviewPanel />}
        {tab === "users" && <UserManagement />}
        {tab === "audit" && <AuditLogPanel />}
        {tab === "advertising" && <AdvertisingPanel />}
      </div>
    </div>
  );
}
