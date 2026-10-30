import createClient from "openapi-fetch";
import { activeLocale, hasMessage, tr } from "@/i18n/runtime";
import type { paths } from "./dto";
import type { ConfigProblem, ErrorBody } from "./types";

export const API_BASE = "/api/v1";

/** A refusal from the API, with its stable code and the message for people. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly messageId: string | null = null,
    readonly args: Record<string, string | number> = {},
    readonly problems: ConfigProblem[] = [], // where a refused configuration goes wrong
  ) {
    super(message);
    this.name = "ApiError";
  }

  get notFound(): boolean {
    return this.status === 404;
  }

  get unauthenticated(): boolean {
    return this.status === 401;
  }
}

/** A 404: the thing asked for does not exist (or not for this reader). */
export const isMissing = (error: unknown): boolean => error instanceof ApiError && error.status === 404;

let csrfToken: string | null = null;

/** The token from `GET /me`, sent back on every unsafe request (sign-in and invitations need none). */
export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

const origin = () => (typeof window === "undefined" ? "" : window.location.origin);

/**
 * The typed client generated from `web/openapi.json`. Every request carries the active locale
 * (the server renders its texts in it) and, when unsafe, the CSRF token.
 */
export const client = createClient<paths>({
  baseUrl: origin(),
  credentials: "same-origin",
  // resolved per call: the test setup and the mock worker replace fetch after this module loads
  fetch: (request) => globalThis.fetch(request),
});

client.use({
  onRequest({ request }) {
    request.headers.set("Accept-Language", activeLocale());
    if (request.method !== "GET" && csrfToken) request.headers.set("X-CSRF-Token", csrfToken);
    return request;
  },
});

/** `url("/journal/stream", {...})` for what openapi-fetch does not carry (EventSource). */
export function url(path: string, query?: Record<string, string | number | undefined | null>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const search = params.toString();
  return `${API_BASE}${path}${search ? `?${search}` : ""}`;
}

/** The data of a call, or the API's refusal as an ApiError; a network failure says Nestor is down. */
export async function unwrap<T>(call: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  let result: Awaited<typeof call>;
  try {
    result = await call;
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "network", tr("error-network"), "error-network");
  }
  if (result.response.ok) return result.data as T;
  throw toError(result.response.status, result.error);
}

function toError(status: number, data: unknown): ApiError {
  const error = (data as Partial<ErrorBody> | undefined)?.error;
  if (error?.message) {
    return new ApiError(
      status,
      error.code ?? "error",
      error.message,
      error.message_id ?? null,
      error.args ?? {},
      error.problems ?? [],
    );
  }
  if (status === 401)
    return new ApiError(status, "unauthenticated", tr("error-unauthenticated"), "error-unauthenticated");
  if (status === 403) return new ApiError(status, "forbidden", tr("error-forbidden"), "error-forbidden");
  if (status === 404) return new ApiError(status, "not_found", tr("error-not-found"), "error-not-found");
  return new ApiError(status, "error", tr("error-status", { status }), "error-status", { status });
}

/**
 * The message to show for any failure: the catalogue's wording when it knows the server's
 * `message_id` (so it follows a locale switch), else the text the server rendered.
 */
export function messageOf(error: unknown): string {
  if (error instanceof ApiError) {
    return error.messageId && hasMessage(error.messageId) ? tr(error.messageId, error.args) : error.message;
  }
  return tr("error-unexpected");
}
