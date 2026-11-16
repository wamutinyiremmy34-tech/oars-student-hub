import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { startDownload } from "@/lib/navigation";
import { detail } from "@/test/fixtures";
import { apiError, mockApi, ok, signedInWith, signedOutApi } from "@/test/mock-api";
import { renderApp } from "@/test/render";

vi.mock("@/lib/navigation", () => ({ startDownload: vi.fn() }));
beforeEach(() => vi.mocked(startDownload).mockClear());

const resourceRoute = (body: unknown) => ({ "GET /resources/r-1": () => ok(body) });

describe("ResourceDetailPage", () => {
  it("asks visitors to sign in instead of offering a download", async () => {
    mockApi({ ...signedOutApi(), ...resourceRoute(detail({}, { can_download: false, download_block_reason: "authentication_required" })) });
    renderApp("/resources/r-1");
    expect(await screen.findByRole("heading", { name: "Calculus Lecture Notes" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in to download" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^download/i })).not.toBeInTheDocument();
    expect(screen.getByText("Full description of the notes.")).toBeInTheDocument();
  });

  it("downloads a free resource through a freshly requested, API-origin link", async () => {
    const api = mockApi({
      ...signedInWith(["order:create"]),
      ...resourceRoute(detail()),
      "POST /resources/r-1/download": () => ok({ url: "/api/v1/downloads/tok-123", expires_in: 60, filename: "notes.pdf", delivery: "STREAM" }),
    });
    renderApp("/resources/r-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: /download/i }));
    await waitFor(() => expect(startDownload).toHaveBeenCalledWith(expect.stringMatching(/\/api\/v1\/downloads\/tok-123$/)));
    expect(api.callsTo("POST /resources/r-1/download")).toHaveLength(1);
  });

  it("shows the server's refusal if a download is denied", async () => {
    mockApi({
      ...signedInWith([]),
      ...resourceRoute(detail()),
      "POST /resources/r-1/download": () => apiError(403, "premium_required", "This is a premium resource. You need access to download it."),
    });
    renderApp("/resources/r-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: /download/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/premium resource/i);
    expect(startDownload).not.toHaveBeenCalled();
  });

  it("shows the premium access screen, with price and preview, and no download button", async () => {
    mockApi({
      ...signedInWith([]),
      ...resourceRoute(detail({ access_type: "PREMIUM", price_ugx: 5000, preview_text: "Sample of question one." }, { can_download: false, download_block_reason: "premium_required" })),
    });
    renderApp("/resources/r-1");
    expect(await screen.findByRole("heading", { name: "Premium resource" })).toBeInTheDocument();
    expect(screen.getAllByText(/UGX 5,000/).length).toBeGreaterThan(0);
    expect(screen.getByText("Sample of question one.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /download/i })).not.toBeInTheDocument();
    expect(screen.getByText(/online purchase isn't available yet/i)).toBeInTheDocument(); // honest: no fake buy button
  });

  it("offers the download once the viewer is entitled", async () => {
    mockApi({ ...signedInWith([]), ...resourceRoute(detail({ access_type: "PREMIUM", price_ugx: 5000 }, { can_download: true, entitlement_status: "ACTIVE" })) });
    renderApp("/resources/r-1");
    expect(await screen.findByRole("button", { name: /download/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Premium resource" })).not.toBeInTheDocument();
  });

  it("tells owners about an unpublished or rejected resource", async () => {
    mockApi({
      ...signedInWith(["resource:create"]),
      ...resourceRoute(detail({ status: "REJECTED", latest_review: { decision: "REJECTED", reason: "Scan is unreadable", created_at: "2026-10-02T08:00:00Z" } }, { is_owner: true })),
    });
    renderApp("/resources/r-1");
    expect(await screen.findByText(/only you and reviewers can see it/i)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Scan is unreadable");
    expect(screen.getByRole("link", { name: "Manage this resource" })).toHaveAttribute("href", "/provider/resources/r-1");
  });

  it("shows a friendly page when the resource is not found or not public", async () => {
    mockApi({ ...signedOutApi(), "GET /resources/r-1": () => apiError(404, "not_found") });
    renderApp("/resources/r-1");
    expect(await screen.findByRole("heading", { name: "Resource not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse resources" })).toBeInTheDocument();
  });
});

describe("ModerationPanel", () => {
  const reviewer = (status: string, flags: Record<string, unknown> = { can_review: true }) =>
    ({ ...signedInWith(["resource:review"]), ...resourceRoute(detail({ status }, { is_owner: false, ...flags })) });

  it("does not render for people without moderation rights", async () => {
    mockApi({ ...signedInWith([]), ...resourceRoute(detail()) });
    renderApp("/resources/r-1");
    await screen.findByRole("heading", { name: "Calculus Lecture Notes" });
    expect(screen.queryByRole("heading", { name: "Moderation" })).not.toBeInTheDocument();
  });

  it("starts a review", async () => {
    const api = mockApi({ ...reviewer("SUBMITTED"), "POST /resources/r-1/start-review": () => ok(detail({ status: "UNDER_REVIEW" })) });
    renderApp("/resources/r-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Start review" }));
    await waitFor(() => expect(api.callsTo("POST /resources/r-1/start-review")).toHaveLength(1));
  });

  it("requires a reason before rejecting and sends it", async () => {
    const api = mockApi({ ...reviewer("UNDER_REVIEW"), "POST /resources/r-1/reject": () => ok(detail({ status: "REJECTED" })) });
    renderApp("/resources/r-1");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Reject…" }));
    const confirm = screen.getByRole("button", { name: "Confirm rejection" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText(/reason for rejection/i), "Unreadable scan");
    await user.click(confirm);
    await waitFor(() => expect(api.callsTo("POST /resources/r-1/reject")[0]?.body).toEqual({ reason: "Unreadable scan" }));
  });

  it("publishes approved resources only for people who may publish", async () => {
    mockApi(reviewer("APPROVED", { can_review: true, can_publish: false }));
    const { unmount } = renderApp("/resources/r-1");
    await screen.findByRole("heading", { name: "Calculus Lecture Notes" });
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
    unmount();

    const api = mockApi({ ...reviewer("APPROVED", { can_review: true, can_publish: true }), "POST /resources/r-1/publish": () => ok(detail({ status: "PUBLISHED" })) });
    renderApp("/resources/r-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Publish" }));
    await waitFor(() => expect(api.callsTo("POST /resources/r-1/publish")).toHaveLength(1));
  });

  it("surfaces the server's refusal (for example separation of duties)", async () => {
    mockApi({ ...reviewer("SUBMITTED"), "POST /resources/r-1/start-review": () => apiError(403, "cannot_review_own", "You cannot moderate your own resource.") });
    renderApp("/resources/r-1");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Start review" }));
    expect(await screen.findByText("You cannot moderate your own resource.")).toBeInTheDocument();
  });
});
