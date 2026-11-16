export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: FieldError[];
  readonly requestId: string | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    details?: FieldError[] | null;
    requestId?: string | null;
  }) {
    super(init.message);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.details = init.details ?? [];
    this.requestId = init.requestId ?? null;
  }
}

export class NetworkError extends Error {
  constructor() {
    super("Network request failed");
    this.name = "NetworkError";
  }
}

export class RequestTimeoutError extends Error {
  constructor() {
    super("Request timed out");
    this.name = "RequestTimeoutError";
  }
}

const GENERIC_SERVER_MESSAGE = "Something went wrong on our side. Please try again.";

const MESSAGES: Record<string, string> = {
  unauthorized: "Please sign in to continue.",
  invalid_token: "Your session has expired. Please sign in again.",
  invalid_refresh_token: "Your session has expired. Please sign in again.",
  invalid_credentials: "Incorrect email or password.",
  account_suspended: "This account has been suspended. Contact support if you think this is a mistake.",
  origin_not_allowed: "This request was blocked for your security. Reload the page and try again.",
  forbidden: "You don't have permission to do that.",
  not_found: "We couldn't find what you were looking for.",
  validation_error: "Please check the highlighted fields and try again.",
  rate_limited: "Too many attempts. Please wait a moment and try again.",
  not_ready: "The service is temporarily unavailable. Please try again shortly.",
  service_unavailable: "The service is temporarily unavailable. Please try again shortly.",
  provider_unavailable: "The payment provider is temporarily unavailable. Please try again shortly.",
  internal_error: GENERIC_SERVER_MESSAGE,
  invalid_response: GENERIC_SERVER_MESSAGE,
};

function isOffline(): boolean {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

/** Turns any thrown value into a message that is safe and understandable for end users. */
export function toUserMessage(error: unknown): string {
  if (error instanceof RequestTimeoutError) {
    return "The request took too long. Check your connection and try again.";
  }
  if (error instanceof NetworkError) {
    return isOffline()
      ? "You're offline. Reconnect and try again."
      : "Couldn't reach the server. Check your connection and try again.";
  }
  if (error instanceof ApiError) {
    const mapped = MESSAGES[error.code];
    if (mapped) return mapped;
    return error.status >= 500 ? GENERIC_SERVER_MESSAGE : error.message || GENERIC_SERVER_MESSAGE;
  }
  return GENERIC_SERVER_MESSAGE;
}

/** Retry only transient failures (network, timeout, 5xx), at most twice. Never retry 4xx. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) return false;
  if (error instanceof ApiError) return error.status >= 500;
  return error instanceof NetworkError || error instanceof RequestTimeoutError;
}
