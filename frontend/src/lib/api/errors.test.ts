import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  NetworkError,
  RequestTimeoutError,
  shouldRetry,
  toUserMessage,
} from "@/lib/api/errors";

afterEach(() => vi.restoreAllMocks());

const apiError = (status: number, code: string, message = "server text") =>
  new ApiError({ status, code, message });

describe("toUserMessage", () => {
  it("maps known error codes to friendly messages", () => {
    expect(toUserMessage(apiError(401, "unauthorized"))).toMatch(/sign in/i);
    expect(toUserMessage(apiError(403, "forbidden"))).toMatch(/permission/i);
    expect(toUserMessage(apiError(503, "not_ready"))).toMatch(/temporarily unavailable/i);
    expect(toUserMessage(apiError(429, "rate_limited"))).toMatch(/too many/i);
  });

  it("never shows raw server text for 5xx errors", () => {
    const message = toUserMessage(apiError(500, "something_new", "stack trace here"));
    expect(message).not.toContain("stack trace");
  });

  it("shows server message for unknown 4xx codes", () => {
    expect(toUserMessage(apiError(409, "duplicate_email", "That email is already registered."))).toBe(
      "That email is already registered.",
    );
  });

  it("distinguishes offline from unreachable server", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    expect(toUserMessage(new NetworkError())).toMatch(/offline/i);
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    expect(toUserMessage(new NetworkError())).toMatch(/couldn't reach/i);
  });

  it("maps authentication codes to safe, friendly messages", () => {
    expect(toUserMessage(apiError(401, "invalid_credentials", "Invalid email or password."))).toBe(
      "Incorrect email or password.",
    );
    expect(toUserMessage(apiError(403, "account_suspended"))).toMatch(/suspended/i);
    expect(toUserMessage(apiError(401, "invalid_refresh_token"))).toMatch(/sign in again/i);
  });

  it("handles timeouts and unknown values", () => {
    expect(toUserMessage(new RequestTimeoutError())).toMatch(/too long/i);
    expect(toUserMessage("boom")).toMatch(/something went wrong/i);
  });
});

describe("shouldRetry", () => {
  it("retries transient failures at most twice", () => {
    expect(shouldRetry(0, new NetworkError())).toBe(true);
    expect(shouldRetry(1, new RequestTimeoutError())).toBe(true);
    expect(shouldRetry(0, apiError(503, "not_ready"))).toBe(true);
    expect(shouldRetry(2, new NetworkError())).toBe(false);
  });

  it("does not retry client errors", () => {
    expect(shouldRetry(0, apiError(401, "unauthorized"))).toBe(false);
    expect(shouldRetry(0, apiError(422, "validation_error"))).toBe(false);
  });
});
