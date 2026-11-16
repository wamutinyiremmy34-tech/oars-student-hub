import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { Alert } from "@/components/ui/Alert";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { AccessBadge, StatusBadge } from "@/features/resources/Badges";
import { BookmarkButton } from "@/features/resources/BookmarkButton";
import { createPayment, getPaymentConfig } from "@/features/payments/api";
import { goToCheckout } from "@/features/payments/checkout";
import { ModerationPanel } from "@/features/resources/ModerationPanel";
import { getResource, requestDownload, type ResourceDetail } from "@/features/resources/api";
import { ApiError, toUserMessage } from "@/lib/api/errors";
import { fileKind, formatBytes, formatUgx } from "@/lib/format";
import { newKey } from "@/lib/id";
import { startDownload } from "@/lib/navigation";

function PremiumAccess({ resource }: { resource: ResourceDetail }) {
  const navigate = useNavigate();
  const config = useQuery({ queryKey: ["payments", "config"], queryFn: ({ signal }) => getPaymentConfig(signal), staleTime: 60_000, retry: false });
  const buy = useMutation({
    mutationFn: () => createPayment({ resource_id: resource.id }, newKey()),
    onSuccess: (payment) => payment.checkout_url && goToCheckout(payment.checkout_url, navigate),
  });
  const available = config.data?.online_available === true;
  return (
    <Card className="space-y-3 border-warning" aria-label="Premium access">
      <h2 className="text-lg font-bold">Premium resource</h2>
      <p>
        This resource costs <strong>{formatUgx(resource.price_ugx ?? 0)}</strong>. You don't have access yet.
      </p>
      {available ? (
        <>
          <Button size="lg" onClick={() => buy.mutate()} disabled={buy.isPending}>
            {buy.isPending ? "Opening checkout…" : `Buy for ${formatUgx(resource.price_ugx ?? 0)}`}
          </Button>
          <p className="text-xs text-fg-muted">Access is unlocked only after the payment is confirmed by our server, not by this page.</p>
          {buy.isError && <Alert variant="error">{toUserMessage(buy.error)}</Alert>}
        </>
      ) : (
        <p className="text-sm text-fg-muted">
          Online purchase isn't available yet. If you've already paid or been given access, contact your university's
          administrator.
        </p>
      )}
    </Card>
  );
}

function AccessPanel({ resource }: { resource: ResourceDetail }) {
  const location = useLocation();
  const download = useMutation({
    mutationFn: () => requestDownload(resource.id),
    onSuccess: (link) => startDownload(link.url),
  });
  const { viewer } = resource;

  if (viewer.can_download) {
    return (
      <div className="space-y-3">
        <Button size="lg" className="w-full sm:w-auto" disabled={download.isPending} onClick={() => download.mutate()}>
          {download.isPending ? "Preparing…" : "Download"}
          {resource.file ? ` (${fileKind(resource.file.mime_type)}, ${formatBytes(resource.file.size_bytes)})` : ""}
        </Button>
        {download.isError && <Alert variant="error">{toUserMessage(download.error)}</Alert>}
      </div>
    );
  }
  if (viewer.download_block_reason === "authentication_required") {
    return (
      <div className="space-y-3">
        <p className="text-fg-muted">
          {resource.access_type === "PREMIUM" ? "Sign in to check your access to this premium resource." : "Sign in to download this resource."}
        </p>
        <Link to="/login" state={{ from: location.pathname }} className={buttonClasses({ size: "lg" })}>
          Sign in to download
        </Link>
      </div>
    );
  }
  if (viewer.download_block_reason === "premium_required") return <PremiumAccess resource={resource} />;
  return <Alert variant="info">This resource isn't available for download.</Alert>;
}

export function ResourceDetailPage() {
  const { id = "" } = useParams();
  const query = useQuery({
    queryKey: ["resources", "detail", id],
    queryFn: ({ signal }) => getResource(id, signal),
    retry: false,
  });

  if (query.isPending) return <p role="status" className="text-fg-muted">Loading…</p>;
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404;
    return (
      <Card className="space-y-3">
        <h1 className="text-2xl font-extrabold">{notFound ? "Resource not found" : "Couldn't load this resource"}</h1>
        <p className="text-fg-muted">{notFound ? "It may have been removed or isn't published." : toUserMessage(query.error)}</p>
        <Link to="/resources" className={buttonClasses({ variant: "secondary" })}>
          Browse resources
        </Link>
      </Card>
    );
  }

  const resource = query.data;
  const published = resource.status === "PUBLISHED";
  return (
    <div className="space-y-6">
      <Card className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <AccessBadge access={resource.access_type} price={resource.price_ugx} />
          <StatusBadge status={resource.status} />
          <span className="text-sm text-fg-muted">{resource.category.name}</span>
        </div>
        <h1 className="text-2xl font-extrabold leading-tight">{resource.title}</h1>
        <p className="text-sm text-fg-muted">
          {resource.institution_name} · by {resource.provider_name}
          {resource.academic_year ? ` · ${resource.academic_year}` : ""}
        </p>

        {!published && (
          <Alert variant="info">
            This resource is <strong>{resource.status.toLowerCase().replace("_", " ")}</strong>. Only you and reviewers can see it.
          </Alert>
        )}
        {resource.latest_review?.decision === "REJECTED" && resource.status !== "PUBLISHED" && (
          <Alert variant="error">Rejected: {resource.latest_review.reason}</Alert>
        )}

        {resource.courses.length > 0 && (
          <ul className="flex flex-wrap gap-2" aria-label="Courses">
            {resource.courses.map((course) => (
              <li key={course.id}>
                <Link to={`/resources?course_id=${course.id}`} className="rounded-full border border-line px-3 py-1 text-sm hover:bg-surface">
                  {course.code} · {course.title}
                </Link>
              </li>
            ))}
          </ul>
        )}
        {resource.description && <p className="whitespace-pre-line">{resource.description}</p>}
        {resource.tags.length > 0 && (
          <ul className="flex flex-wrap gap-1" aria-label="Tags">
            {resource.tags.map((tag) => (
              <li key={tag} className="rounded-full bg-surface px-2 py-0.5 text-xs text-fg-muted">#{tag}</li>
            ))}
          </ul>
        )}
      </Card>

      {resource.preview_text && (
        <Card className="space-y-2" aria-label="Preview">
          <h2 className="text-lg font-bold">Preview</h2>
          <p className="whitespace-pre-line text-fg-muted">{resource.preview_text}</p>
        </Card>
      )}

      <AccessPanel resource={resource} />

      <div className="flex flex-wrap gap-2">
        <BookmarkButton resourceId={resource.id} bookmarked={resource.viewer.is_bookmarked} />
        {resource.viewer.is_owner && (
          <Link to={`/provider/resources/${resource.id}`} className={buttonClasses({ variant: "secondary" })}>
            Manage this resource
          </Link>
        )}
      </div>

      <ModerationPanel resource={resource} />
    </div>
  );
}
