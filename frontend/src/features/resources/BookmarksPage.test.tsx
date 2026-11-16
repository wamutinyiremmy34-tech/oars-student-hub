import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { summary } from "@/test/fixtures";
import { mockApi, okPage, signedInWith, signedOutApi } from "@/test/mock-api";
import { renderApp } from "@/test/render";

describe("BookmarksPage", () => {
  it("redirects visitors to sign in", async () => {
    mockApi(signedOutApi());
    renderApp("/bookmarks");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("lists saved resources", async () => {
    mockApi({ ...signedInWith([]), "GET /bookmarks": () => okPage([summary({ is_bookmarked: true })]) });
    renderApp("/bookmarks");
    expect(await screen.findByRole("link", { name: "Calculus Lecture Notes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Saved ✓" })).toHaveAttribute("aria-pressed", "true");
  });

  it("shows an empty state", async () => {
    mockApi({ ...signedInWith([]), "GET /bookmarks": () => okPage([]) });
    renderApp("/bookmarks");
    expect(await screen.findByText("You haven't saved anything yet.")).toBeInTheDocument();
  });
});
