import type { NavigateFunction } from "react-router-dom";
import { redirectTo } from "@/lib/navigation";

/** In-app checkout paths use the router; a real provider's hosted page is an absolute URL. */
export function goToCheckout(url: string, navigate: NavigateFunction): void {
  if (url.startsWith("/")) navigate(url);
  else redirectTo(url);
}
