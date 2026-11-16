import { z } from "zod";
import { ApiError, NetworkError, RequestTimeoutError } from "@/lib/api/errors";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";
const DEFAULT_TIMEOUT_MS = 15_000;

/**
 * Connects the HTTP client to the auth feature without a circular import.
 * The access token lives only in memory (never localStorage); the refresh token is an HttpOnly cookie
 * that JavaScript cannot read.
 */
export interface AuthHandler {
  getAccessToken(): string | null;
  /** Resolves a fresh access token, or null when the session can no longer be refreshed. */
  refresh(): Promise<string | null>;
}

let authHandler: AuthHandler | null = null;

export function setAuthHandler(handler: AuthHandler | null): void {
  authHandler = handler;
}

const errorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.array(z.object({ field: z.string(), message: z.string() })).nullish(),
    request_id: z.string().nullish(),
  }),
});

export function envelopeOf<S extends z.ZodType>(data: S) {
  return z.object({ data, meta: z.record(z.string(), z.unknown()).optional() });
}

export interface RequestOptions<S extends z.ZodType> {
  schema: S;
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** false = never attach the access token (login, register, refresh, logout). */
  auth?: boolean;
  /** true = on 401, do not try to refresh the session and retry. */
  skipAuthRefresh?: boolean;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function toApiError(status: number, payload: unknown): ApiError {
  const parsed = errorEnvelopeSchema.safeParse(payload);
  if (parsed.success) {
    const { code, message, details, request_id } = parsed.data.error;
    return new ApiError({ status, code, message, details, requestId: request_id });
  }
  return new ApiError({ status, code: "http_error", message: "The server returned an error." });
}

interface Envelope<T> {
  data: T;
  meta: Record<string, unknown>;
}

async function execute<S extends z.ZodType>(
  path: string,
  options: RequestOptions<S>,
): Promise<Envelope<z.infer<S>>> {
  const {
    schema,
    method = "GET",
    body,
    headers,
    signal,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    auth = true,
  } = options;

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onCallerAbort = () => controller.abort();
  signal?.addEventListener("abort", onCallerAbort, { once: true });
  if (signal?.aborted) controller.abort();

  const accessToken = auth ? (authHandler?.getAccessToken() ?? null) : null;
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  try {
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        method,
        credentials: "include",
        signal: controller.signal,
        headers: {
          Accept: "application/json",
          ...(body !== undefined && !isFormData ? { "Content-Type": "application/json" } : {}),
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          ...headers,
        },
        body: body === undefined ? undefined : isFormData ? (body as FormData) : JSON.stringify(body),
      });
    } catch (error) {
      if (timedOut) throw new RequestTimeoutError();
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new NetworkError();
    }

    const payload = await readJson(response);
    if (!response.ok) throw toApiError(response.status, payload);

    const parsed = envelopeOf(schema).safeParse(payload);
    if (!parsed.success) {
      throw new ApiError({
        status: response.status,
        code: "invalid_response",
        message: "The server returned an unexpected response.",
      });
    }
    return { data: (parsed.data as { data: z.infer<S>; meta?: Record<string, unknown> }).data, meta: (parsed.data as { data: z.infer<S>; meta?: Record<string, unknown> }).meta ?? {} };
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onCallerAbort);
  }
}

async function request<S extends z.ZodType>(
  path: string,
  options: RequestOptions<S>,
): Promise<Envelope<z.infer<S>>> {
  try {
    return await execute(path, options);
  } catch (error) {
    const canRefresh =
      error instanceof ApiError &&
      error.status === 401 &&
      authHandler !== null &&
      options.auth !== false &&
      !options.skipAuthRefresh;
    if (canRefresh && (await authHandler?.refresh())) {
      return execute(path, options); // the handler's token store now holds the new access token
    }
    throw error;
  }
}

/**
 * Typed fetch for the OARS API. Validates the success envelope with the given Zod schema,
 * converts error envelopes into ApiError, and maps network failures and timeouts to typed errors.
 * A 401 on an authenticated call triggers one session refresh and one retry.
 */
export async function apiFetch<S extends z.ZodType>(
  path: string,
  options: RequestOptions<S>,
): Promise<z.infer<S>> {
  return (await request(path, options)).data;
}

const pageMetaSchema = z.object({
  page: z.number().int(),
  page_size: z.number().int(),
  total: z.number().int(),
});
export type PageMeta = z.infer<typeof pageMetaSchema>;

export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

/** For list endpoints that return {data: [...], meta: {page, page_size, total}}. */
export async function apiFetchPage<S extends z.ZodType>(
  path: string,
  options: RequestOptions<z.ZodArray<S>>,
): Promise<Page<z.infer<S>>> {
  const { data, meta } = await request(path, options);
  const parsed = pageMetaSchema.safeParse(meta);
  return {
    items: data as z.infer<S>[],
    meta: parsed.success ? parsed.data : { page: 1, page_size: data.length, total: data.length },
  };
}

/** Resolves a server-relative path (such as a download link) against the API's origin, not the web app's. */
export function resolveApiUrl(path: string): string {
  return new URL(path, new URL(API_BASE_URL, window.location.origin)).toString();
}
