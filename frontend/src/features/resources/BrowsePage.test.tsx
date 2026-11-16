import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CATEGORIES, INSTITUTIONS, summary } from "@/test/fixtures";
import { apiError, mockApi, ok, okPage, signedInWith, signedOutApi } from "@/test/mock-api";
import { renderApp } from "@/test/render";

const base = () => ({
  ...signedOutApi(),
  "GET /institutions": () => ok(INSTITUTIONS),
  "GET /categories": () => ok(CATEGORIES),
  "GET /search": () =>
    okPage([summary(), summary({ id: "r-2", title: "Data Structures Past Paper", access_type: "PREMIUM", price_ugx: 5000 })], { total: 2 }),
});

describe("BrowsePage", () => {
  it("lists published resources with free and premium badges", async () => {
    mockApi(base());
    renderApp("/resources");
    expect(await screen.findByRole("link", { name: "Calculus Lecture Notes" })).toHaveAttribute("href", "/resources/r-1");
    expect(screen.getByText("Free")).toBeInTheDocument();
    expect(screen.getByText("Premium · UGX 5,000")).toBeInTheDocument();
    expect(screen.getByText("2 resources found")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument(); // visitors cannot bookmark
  });

  it("searches only when submitted and keeps the query in the URL", async () => {
    const api = mockApi(base());
    const { router } = renderApp("/resources");
    await screen.findByRole("link", { name: "Calculus Lecture Notes" });
    const before = api.callsTo("GET /search").length;

    await userEvent.setup().type(screen.getByLabelText(/search notes/i), "calculus");
    expect(api.callsTo("GET /search")).toHaveLength(before); // typing alone sends nothing (saves mobile data)

    await userEvent.setup().click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(api.callsTo("GET /search").at(-1)?.search.get("q")).toBe("calculus"));
    expect(router.state.location.search).toContain("q=calculus");
  });

  it("applies filters and returns to page one", async () => {
    const api = mockApi(base());
    renderApp("/resources?page=3");
    await screen.findByRole("link", { name: "Calculus Lecture Notes" });
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Type"), "notes");
    await user.selectOptions(screen.getByLabelText("Price"), "PREMIUM");
    await user.selectOptions(await screen.findByLabelText("University"), "i-1");
    await waitFor(() => {
      const last = api.callsTo("GET /search").at(-1)!.search;
      expect(last.get("category")).toBe("notes");
      expect(last.get("access")).toBe("PREMIUM");
      expect(last.get("institution_id")).toBe("i-1");
      expect(last.get("page")).toBeNull();
    });
  });

  it("paginates with small pages", async () => {
    const api = mockApi({ ...base(), "GET /search": () => okPage([summary()], { page: 1, total: 30 }) });
    renderApp("/resources");
    expect(await screen.findByText("Page 1 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(api.callsTo("GET /search").at(-1)?.search.get("page")).toBe("2"));
    expect(api.calls.every((c) => Number(c.search.get("page_size") ?? 12) <= 12)).toBe(true);
  });

  it("shows an empty state and a friendly error with retry", async () => {
    mockApi({ ...base(), "GET /search": () => okPage([]) });
    const { unmount } = renderApp("/resources");
    expect(await screen.findByText("No resources found.")).toBeInTheDocument();
    unmount();

    let calls = 0;
    mockApi({ ...base(), "GET /search": () => (++calls === 1 ? apiError(503, "service_unavailable") : okPage([summary()])) });
    renderApp("/resources");
    expect(await screen.findByRole("alert")).toHaveTextContent(/temporarily unavailable/i);
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Calculus Lecture Notes" })).toBeInTheDocument();
  });

  it("filters by course and lets the user clear it", async () => {
    const api = mockApi(base());
    renderApp("/resources?course_id=co-1");
    expect(await screen.findByText(/showing resources for one course/i)).toBeInTheDocument();
    expect(api.callsTo("GET /search")[0]?.search.get("course_id")).toBe("co-1");
    await userEvent.setup().click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(api.callsTo("GET /search").at(-1)?.search.get("course_id")).toBeNull());
  });

  it("lets signed-in students save a resource", async () => {
    const api = mockApi({ ...signedInWith(["order:create"]), ...base(), "POST /auth/refresh": () => ok({ access_token: "t", token_type: "bearer", expires_in: 900 }), "PUT /bookmarks/r-1": () => ok({ message: "Bookmarked." }) });
    renderApp("/resources");
    const card = (await screen.findByRole("link", { name: "Calculus Lecture Notes" })).closest("li")!;
    await userEvent.setup().click(await within(card).findByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.callsTo("PUT /bookmarks/r-1")).toHaveLength(1));
  });
});
