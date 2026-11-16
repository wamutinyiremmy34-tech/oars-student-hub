/** Isolated so tests can replace it: jsdom cannot navigate. */
export function startDownload(url: string): void {
  window.location.assign(url);
}

/** Leaves the app for a provider's hosted checkout (an absolute URL); in-app checkout paths use the router. */
export function redirectTo(url: string): void {
  window.location.assign(url);
}
