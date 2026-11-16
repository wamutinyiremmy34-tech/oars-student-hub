import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CATEGORIES, detail, INSTITUTIONS, summary } from "@/test/fixtures";
import { apiError, mockApi, ok, okPage, signedInWith, signedOutApi } from "@/test/mock-api";
import { renderApp } from "@/test/render";

const refs = () => ({ "GET /institutions": () => ok(INSTITUTIONS), "GET /categories": () => ok(CATEGORIES) });
const provider = () => ({ ...signedInWith(["resource:create", "resource:update", "resource:submit"]), ...refs() });

describe("provider pages", () => {
  it("deny people without the provider permission (UX gate; the API enforces it too)", async () => {
    mockApi(signedInWith(["order:create"]));
    renderApp("/provider/resources");
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

  it("require sign-in", async () => {
    mockApi(signedOutApi());
    renderApp("/provider/resources/new");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("list my resources with their review status", async () => {
    mockApi({ ...provider(), "GET /resources/mine": () => okPage([summary({ status: "REJECTED" }), summary({ id: "r-2", title: "Second", status: "DRAFT" })]) });
    renderApp("/provider/resources");
    expect(await screen.findByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New resource" })).toHaveAttribute("href", "/provider/resources/new");
  });

  it("creates a draft with normalised tags and no price for free resources", async () => {
    const api = mockApi({
      ...provider(),
      "POST /resources": () => ok(detail({ id: "r-new", status: "DRAFT" }, { is_owner: true }), 201),
      "GET /resources/r-new": () => ok(detail({ id: "r-new", status: "DRAFT" }, { is_owner: true })),
    });
    renderApp("/provider/resources/new");
    const user = userEvent.setup();
    const uniSelect = await screen.findByLabelText("University");
    await screen.findByText("Makerere University"); // wait for options to load
    await user.selectOptions(uniSelect, "i-1");
    await user.selectOptions(screen.getByLabelText("Type"), "c-1");
    await user.type(screen.getByLabelText("Title"), "Calculus notes");
    await user.type(screen.getByLabelText(/tags/i), "Calculus, year-1 , calculus");
    await user.click(screen.getByRole("button", { name: "Create draft" }));

    await waitFor(() => expect(api.callsTo("POST /resources")).toHaveLength(1));
    expect(api.callsTo("POST /resources")[0]?.body).toEqual({
      institution_id: "i-1", category_id: "c-1", title: "Calculus notes", description: "",
      access_type: "FREE", tags: ["calculus", "year-1"], course_ids: [],
    });
    expect(await screen.findByRole("heading", { name: "Edit resource" })).toBeInTheDocument();
  });

  it("requires a whole-number price for premium resources before calling the API", async () => {
    const api = mockApi(provider());
    renderApp("/provider/resources/new");
    const user = userEvent.setup();
    const uniSelect = await screen.findByLabelText("University");
    await screen.findByText("Makerere University"); // wait for options to load
    await user.selectOptions(uniSelect, "i-1");
    await user.selectOptions(screen.getByLabelText("Type"), "c-1");
    await user.type(screen.getByLabelText("Title"), "Premium paper");
    await user.selectOptions(screen.getByLabelText("Access"), "PREMIUM");
    await user.type(screen.getByLabelText("Price (UGX)"), "12.5");
    await user.click(screen.getByRole("button", { name: "Create draft" }));
    expect(await screen.findByText(/whole number of shillings/i)).toBeInTheDocument();
    expect(api.callsTo("POST /resources")).toHaveLength(0);
  });

  it("checks upload size in the browser, then uploads valid files", async () => {
    const draft = detail({ id: "r-1", status: "DRAFT", versions: [] }, { is_owner: true });
    const api = mockApi({
      ...provider(),
      "GET /resources/r-1": () => ok(draft),
      "POST /resources/r-1/versions": () =>
        ok({ id: "v-9", version_number: 1, filename: "notes.pdf", mime_type: "application/pdf", size_bytes: 2048, is_current: false, changelog: null, created_at: "2026-10-03T08:00:00Z" }, 201),
    });
    renderApp("/provider/resources/r-1");
    const input = (await screen.findByLabelText(/upload a new version/i)) as HTMLInputElement;
    const user = userEvent.setup();

    const huge = new File(["x"], "big.pdf", { type: "application/pdf" });
    Object.defineProperty(huge, "size", { value: 26 * 1024 * 1024 });
    await user.upload(input, huge);
    expect(await screen.findByText(/the limit is 25\.0 MB/i)).toBeInTheDocument();
    expect(api.callsTo("POST /resources/r-1/versions")).toHaveLength(0);

    await user.upload(input, new File(["%PDF-1.4"], "notes.pdf", { type: "application/pdf" }));
    await waitFor(() => expect(api.callsTo("POST /resources/r-1/versions")).toHaveLength(1));
    expect(api.callsTo("POST /resources/r-1/versions")[0]?.formData?.get("file")).toBeInstanceOf(File);
    expect(api.callsTo("POST /resources/r-1/versions")[0]?.headers.get("Content-Type")).toBeNull(); // browser sets the multipart boundary
  });

  it("surfaces server-side upload rejections", async () => {
    mockApi({
      ...provider(),
      "GET /resources/r-1": () => ok(detail({ id: "r-1", status: "DRAFT", versions: [] }, { is_owner: true })),
      "POST /resources/r-1/versions": () => apiError(415, "unsupported_file_type", "Only PDF, Word, PowerPoint, Excel, PNG, JPEG and plain-text files are allowed."),
    });
    renderApp("/provider/resources/r-1");
    await userEvent.setup().upload(await screen.findByLabelText(/upload a new version/i), new File(["MZ"], "x.pdf", { type: "application/pdf" }));
    expect(await screen.findByText(/only pdf, word/i)).toBeInTheDocument();
  });

  it("only allows submitting once a file exists, and submits", async () => {
    const version = { id: "v-1", version_number: 1, filename: "notes.pdf", mime_type: "application/pdf", size_bytes: 2048, is_current: false, changelog: null, created_at: "2026-10-03T08:00:00Z" };
    mockApi({ ...provider(), "GET /resources/r-1": () => ok(detail({ id: "r-1", status: "DRAFT", versions: [] }, { is_owner: true })) });
    const first = renderApp("/provider/resources/r-1");
    expect(await screen.findByRole("button", { name: "Submit for review" })).toBeDisabled();
    first.unmount();

    const api = mockApi({
      ...provider(),
      "GET /resources/r-1": () => ok(detail({ id: "r-1", status: "DRAFT", versions: [version] }, { is_owner: true })),
      "POST /resources/r-1/submit": () => ok(detail({ id: "r-1", status: "SUBMITTED" }, { is_owner: true })),
    });
    renderApp("/provider/resources/r-1");
    const button = await screen.findByRole("button", { name: "Submit for review" });
    expect(button).toBeEnabled();
    await userEvent.setup().click(button);
    await waitFor(() => expect(api.callsTo("POST /resources/r-1/submit")).toHaveLength(1));
  });

  it("locks editing while a resource is under review", async () => {
    mockApi({ ...provider(), "GET /resources/r-1": () => ok(detail({ id: "r-1", status: "UNDER_REVIEW" }, { is_owner: true })) });
    renderApp("/provider/resources/r-1");
    expect(await screen.findByText(/can't be edited right now/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/upload a new version/i)).not.toBeInTheDocument();
  });
});

describe("moderation page and navigation", () => {
  it("denies people without resource:review", async () => {
    mockApi(signedInWith(["resource:create"]));
    renderApp("/moderation");
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

  it("lists the queue and filters by status", async () => {
    const api = mockApi({
      ...signedInWith(["resource:review"]),
      "GET /resources/review-queue": () => okPage([summary({ status: "SUBMITTED" })]),
    });
    renderApp("/moderation");
    expect(await screen.findByRole("link", { name: "Open to review" })).toHaveAttribute("href", "/resources/r-1");
    await userEvent.setup().selectOptions(screen.getByLabelText("Show"), "SUBMITTED");
    await waitFor(() => expect(api.callsTo("GET /resources/review-queue").at(-1)?.search.get("status")).toBe("SUBMITTED"));
  });

  it("shows navigation links according to permissions", async () => {
    mockApi(signedInWith(["resource:create", "resource:review"]));
    const first = renderApp("/");
    expect(await screen.findByRole("link", { name: "My resources" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Moderation" })).toBeInTheDocument();
    first.unmount();

    mockApi(signedInWith(["order:create"]));
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Saved" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "My resources" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Moderation" })).not.toBeInTheDocument();
  });
});
