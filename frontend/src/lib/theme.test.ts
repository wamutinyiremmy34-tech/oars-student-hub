import { beforeEach, describe, expect, it } from "vitest";
import {
  applyTheme,
  nextPreference,
  readPreference,
  resolveTheme,
  savePreference,
  THEME_STORAGE_KEY,
} from "@/lib/theme";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.classList.remove("dark");
});

describe("theme", () => {
  it("defaults to system when nothing or garbage is stored", () => {
    expect(readPreference()).toBe("system");
    window.localStorage.setItem(THEME_STORAGE_KEY, "neon");
    expect(readPreference()).toBe("system");
  });

  it("persists a valid preference", () => {
    savePreference("dark");
    expect(readPreference()).toBe("dark");
  });

  it("resolves system using the OS preference", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
  });

  it("toggles the dark class on <html>", () => {
    applyTheme("dark");
    expect(document.documentElement).toHaveClass("dark");
    applyTheme("light");
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("cycles light → dark → system → light", () => {
    expect(nextPreference("light")).toBe("dark");
    expect(nextPreference("dark")).toBe("system");
    expect(nextPreference("system")).toBe("light");
  });
});
