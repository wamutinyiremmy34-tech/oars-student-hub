import { describe, expect, it, vi } from "vitest";
import { applyServerFieldErrors, safeRedirect } from "@/features/auth/forms";
import { ApiError } from "@/lib/api/errors";

describe("safeRedirect", () => {
  it("allows same-site paths", () => {
    expect(safeRedirect("/account?tab=1")).toBe("/account?tab=1");
  });
  it.each(["https://evil.example", "//evil.example", "javascript:alert(1)", undefined, 42])(
    "rejects %s",
    (value) => {
      expect(safeRedirect(value)).toBe("/account");
    },
  );
});

describe("applyServerFieldErrors", () => {
  it("maps known fields and ignores unknown ones", () => {
    const setError = vi.fn();
    const error = new ApiError({
      status: 422,
      code: "validation_error",
      message: "bad",
      details: [
        { field: "body.email", message: "Not valid" },
        { field: "body.mystery", message: "??" },
      ],
    });
    expect(applyServerFieldErrors(error, setError, ["email", "password"])).toBe(true);
    expect(setError).toHaveBeenCalledOnce();
    expect(setError).toHaveBeenCalledWith("email", { type: "server", message: "Not valid" });
  });

  it("returns false for non-API errors", () => {
    expect(applyServerFieldErrors(new Error("x"), vi.fn(), ["email"])).toBe(false);
  });
});
