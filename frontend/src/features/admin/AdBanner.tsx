/**
 * AdBanner: displays an eligible advertisement for a named placement.
 *
 * Impressions are recorded on mount; clicks are recorded before navigation.
 * Event recording failures are silently swallowed so they never break browsing.
 * No personal data is sent; only an anonymous session token.
 */
import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api/client";
import { z } from "zod";

const adSchema = z.object({
  id: z.string(),
  title: z.string(),
  body: z.string().nullable(),
  image_url: z.string().nullable(),
  click_url: z.string().nullable(),
  placement: z.string(),
});
type AdItem = z.infer<typeof adSchema>;

function getOrCreateSessionToken(): string {
  const key = "oars.ad_session";
  let token = sessionStorage.getItem(key);
  if (!token) {
    token = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
    sessionStorage.setItem(key, token);
  }
  return token;
}

async function recordEvent(adId: string, eventType: "IMPRESSION" | "CLICK", institutionId?: string) {
  try {
    await apiFetch(`/ads/${adId}/events`, {
      method: "POST",
      body: {
        event_type: eventType,
        institution_id: institutionId ?? null,
        session_token: getOrCreateSessionToken(),
      },
      schema: z.object({ message: z.string() }),
    });
  } catch {
    // Never let analytics errors affect the UX.
  }
}

export function AdBanner({
  placement = "dashboard_banner",
  institutionId,
}: {
  placement?: string;
  institutionId?: string;
}) {
  const params = new URLSearchParams({ placement, limit: "1" });
  if (institutionId) params.set("institution_id", institutionId);

  const q = useQuery({
    queryKey: ["ads", placement, institutionId],
    queryFn: ({ signal }) =>
      apiFetch(`/ads?${params.toString()}`, {
        schema: z.array(adSchema),
        auth: false,
        signal,
      }),
    staleTime: 5 * 60_000,
    retry: false,
  });

  const ad: AdItem | null = q.data?.[0] ?? null;
  const impressionFired = useRef(false);

  useEffect(() => {
    if (ad && !impressionFired.current) {
      impressionFired.current = true;
      void recordEvent(ad.id, "IMPRESSION", institutionId);
    }
  }, [ad, institutionId]);

  if (!ad) return null;

  function handleClick() {
    if (ad) void recordEvent(ad.id, "CLICK", institutionId);
  }

  return (
    <aside
      aria-label="Advertisement"
      className="rounded-card border border-line bg-raised p-4 text-sm shadow-soft"
    >
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-muted">
        Sponsored
      </p>
      {ad.image_url && (
        <img
          src={ad.image_url}
          alt=""
          aria-hidden="true"
          className="mb-3 w-full rounded-control object-cover"
          style={{ maxHeight: "120px" }}
          loading="lazy"
        />
      )}
      <p className="font-bold">{ad.title}</p>
      {ad.body && <p className="mt-1 text-fg-muted">{ad.body}</p>}
      {ad.click_url && (
        <a
          href={ad.click_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={handleClick}
          className="mt-3 inline-block text-secondary underline hover:no-underline"
        >
          Learn more →
        </a>
      )}
    </aside>
  );
}
