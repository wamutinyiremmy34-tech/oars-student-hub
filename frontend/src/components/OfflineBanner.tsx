import { useOnlineStatus } from "@/lib/use-online-status";

export function OfflineBanner() {
  const online = useOnlineStatus();
  if (online) return null;
  return (
    <div role="status" className="bg-warning px-4 py-2 text-center text-sm font-semibold text-ink">
      You're offline. Some features are unavailable until you reconnect.
    </div>
  );
}
