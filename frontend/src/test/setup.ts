import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { tokenStore, __resetInflightForTest } from "@/features/auth/session";

// ── jsdom + react-router v7 + Node native fetch compatibility ──────────────────
// react-router v7's data router creates Request objects with an AbortSignal for
// navigation abort handling. In jsdom, the AbortSignal is from jsdom's realm, but
// Node's native fetch (undici) rejects it: "Expected signal to be an instance of
// AbortSignal". Stripping the signal in tests is safe — it's only used to cancel
// in-flight navigations, which tests don't need.
const OriginalRequest = globalThis.Request;
class PatchedRequest extends OriginalRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    const { signal: _omit, ...rest } = init ?? {};
    void _omit;
    super(input, rest as RequestInit);
  }
}
globalThis.Request = PatchedRequest as typeof Request;

// ── jsdom v26 removed FileList.prototype.item() ───────────────────────────────
// @testing-library/user-event v14 calls FileList.item(i) internally when
// uploading files. jsdom v26 no longer provides this method, causing
// "_input_files.item is not a function" in upload tests.
if (typeof FileList !== "undefined" && !FileList.prototype.item) {
  FileList.prototype.item = function (index: number): File | null {
    return this[index] ?? null;
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  tokenStore.set(null);
  __resetInflightForTest();
  window.localStorage.clear();
});
