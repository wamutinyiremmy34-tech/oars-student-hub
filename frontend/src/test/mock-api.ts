import { vi } from "vitest";
import type { Me } from "@/features/auth/api";

export interface MockRequest {
  method: string;
  /** Path relative to /api/v1, e.g. "/auth/login". */
  path: string;
  search: URLSearchParams;
  body: unknown;
  formData?: FormData;
  headers: Headers;
}
export type MockHandler = (request: MockRequest) => Response | Promise<Response>;

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function ok(data: unknown, status = 200): Response {
  return jsonResponse({ data, meta: {} }, status);
}

export function apiError(status: number, code: string, message = "Server message"): Response {
  return jsonResponse({ error: { code, message, details: null, request_id: "req-test-0001" } }, status);
}

/**
 * Replaces fetch with a router keyed by "METHOD /path". Any call without a handler is recorded in
 * `unmocked` and fails the request, so tests cannot silently depend on the network.
 */
export function mockApi(routes: Record<string, MockHandler>) {
  const calls: MockRequest[] = [];
  const unmocked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      const path = url.pathname.replace(/^\/api\/v1/, "");
      const method = (init?.method ?? "GET").toUpperCase();
      const request: MockRequest = {
        method,
        path,
        search: url.searchParams,
        body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
        formData: init?.body instanceof FormData ? init.body : undefined,
        headers: new Headers(init?.headers),
      };
      calls.push(request);
      const handler = routes[`${method} ${path}`];
      if (!handler) {
        unmocked.push(`${method} ${path}`);
        throw new TypeError(`Unmocked API call: ${method} ${path}`);
      }
      return handler(request);
    }),
  );
  return { calls, unmocked, callsTo: (key: string) => calls.filter((c) => `${c.method} ${c.path}` === key) };
}

export const TOKEN = {
  access_token: "access-token-1",
  token_type: "bearer",
  expires_in: 900,
};

export const ME: Me = {
  user: {
    id: "u-1",
    email: "amina@example.com",
    full_name: "Amina Nakato",
    phone: null,
    status: "ACTIVE",
    email_verified: false,
    created_at: "2026-10-03T08:00:00Z",
  },
  student_profile: { institution_id: "i-1", program_id: null, student_number: null, year_of_study: null },
  roles: [{ role: "STUDENT", institution_id: "i-1" }],
  permissions: [
    { permission: "order:create", institution_id: "i-1" },
    { permission: "notification:read", institution_id: "i-1" },
  ],
};

export const ME_PROVIDER: Me = {
  ...ME,
  user: { ...ME.user, id: "u-2", email: "provider@demo.oars.dev", full_name: "Demo Provider" },
  student_profile: null,
  roles: [{ role: "RESOURCE_PROVIDER", institution_id: "i-1" }],
  permissions: [
    { permission: "resource:create", institution_id: "i-1" },
    { permission: "notification:read", institution_id: "i-1" },
  ],
};

export const ME_OPERATOR: Me = {
  ...ME,
  user: { ...ME.user, id: "u-3", email: "operator@demo.oars.dev", full_name: "Demo Operator" },
  student_profile: null,
  roles: [{ role: "PRINTING_OPERATOR", institution_id: "i-1" }],
  permissions: [
    { permission: "order:read_any", institution_id: "i-1" },
    { permission: "notification:read", institution_id: "i-1" },
  ],
};

export const ME_ADMIN: Me = {
  ...ME,
  user: { ...ME.user, id: "u-4", email: "admin@demo.oars.dev", full_name: "Demo Admin" },
  student_profile: null,
  roles: [{ role: "ADMIN", institution_id: null }],
  permissions: [
    { permission: "user:read", institution_id: null },
    { permission: "user:suspend", institution_id: null },
    { permission: "role:assign", institution_id: null },
    { permission: "resource:review", institution_id: null },
    { permission: "advertisement:manage", institution_id: null },
    { permission: "analytics:read", institution_id: null },
    { permission: "notification:read", institution_id: null },
  ],
};

/** A minimal dashboard API response for the /dashboard endpoint. */
export const DASHBOARD = {
  greeting: "Good morning!",
  unread_notifications: 0,
  recent_resources: [],
  recent_orders: [],
  bookmarked_count: 0,
};

/** The common starting point: a visitor with no session. */
export const signedOutApi = (): Record<string, MockHandler> => ({
  "POST /auth/refresh": () => apiError(401, "invalid_refresh_token"),
});

/** A visitor whose refresh cookie is still valid. */
export const signedInApi = (): Record<string, MockHandler> => ({
  "POST /auth/refresh": () => ok(TOKEN),
  "GET /me": () => ok(ME),
  "POST /auth/logout": () => ok({ message: "Signed out." }),
  "GET /notifications/unread-count": () => ok({ count: 0 }),
});

/** Signed-in as a resource provider. */
export const signedInAsProvider = (): Record<string, MockHandler> => ({
  "POST /auth/refresh": () => ok(TOKEN),
  "GET /me": () => ok(ME_PROVIDER),
  "POST /auth/logout": () => ok({ message: "Signed out." }),
  "GET /notifications/unread-count": () => ok({ count: 0 }),
});

/** Signed-in as a printing operator. */
export const signedInAsOperator = (): Record<string, MockHandler> => ({
  "POST /auth/refresh": () => ok(TOKEN),
  "GET /me": () => ok(ME_OPERATOR),
  "POST /auth/logout": () => ok({ message: "Signed out." }),
  "GET /notifications/unread-count": () => ok({ count: 0 }),
});

/** Signed-in as an admin. */
export const signedInAsAdmin = (): Record<string, MockHandler> => ({
  "POST /auth/refresh": () => ok(TOKEN),
  "GET /me": () => ok(ME_ADMIN),
  "POST /auth/logout": () => ok({ message: "Signed out." }),
  "GET /notifications/unread-count": () => ok({ count: 0 }),
});

export function okPage(items: unknown[], meta: { page?: number; page_size?: number; total?: number } = {}): Response {
  return jsonResponse({
    data: items,
    meta: { page: meta.page ?? 1, page_size: meta.page_size ?? 12, total: meta.total ?? items.length },
  });
}

/** A signed-in visitor whose /me reports the given permissions (all unscoped). */
export function signedInWith(permissions: string[]): Record<string, MockHandler> {
  return {
    ...signedInApi(),
    "GET /me": () =>
      ok({ ...ME, permissions: permissions.map((permission) => ({ permission, institution_id: null })) }),
  };
}
