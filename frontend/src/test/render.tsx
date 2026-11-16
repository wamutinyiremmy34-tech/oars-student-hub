import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { routes } from "@/app/routes";
import { AppProviders } from "@/app/providers";

/** Renders the real route tree with real providers; only the network is mocked. */
export function renderApp(path: string, state?: unknown) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter(routes, {
    initialEntries: [state === undefined ? path : { pathname: path, state }],
  });
  const view = render(
    <AppProviders client={client}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...view, router };
}
