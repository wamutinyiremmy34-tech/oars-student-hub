import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mockApi, signedOutApi } from "@/test/mock-api";
import { renderApp } from "@/test/render";

describe("routes", () => {
  it("renders the home page inside the app shell", async () => {
    mockApi(signedOutApi());
    renderApp("/");
    expect(await screen.findByRole("heading", { level: 1, name: "OARS Student Solutions" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to content" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /system status/i })).toHaveAttribute("href", "/status");
    // The homepage has multiple "Sign in" links (nav + hero); verify at least one is present.
    expect((await screen.findAllByRole("link", { name: "Sign in" })).length).toBeGreaterThanOrEqual(1);
  });

  it("renders a not-found page for unknown paths", async () => {
    mockApi(signedOutApi());
    renderApp("/no-such-page");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });
});
