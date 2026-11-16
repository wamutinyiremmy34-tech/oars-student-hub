import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StatusPage } from "@/features/status/StatusPage";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StatusPage />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("StatusPage", () => {
  it("shows readiness reported by the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(jsonResponse({ data: { status: "ready", checks: { database: "ok" } } })),
    );
    renderPage();
    expect(await screen.findByText(/all systems ready/i)).toBeInTheDocument();
    expect(screen.getByText("database: ok")).toBeInTheDocument();
  });

  it("shows a friendly message when the service is not ready", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: "not_ready", message: "Service is not ready.", request_id: "r1" } },
          503,
        ),
      ),
    );
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/temporarily unavailable/i);
    expect(screen.getByRole("button", { name: "Try again" })).toBeEnabled();
  });

  it("shows a connection message when the network fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach the server|offline/i);
  });
});
