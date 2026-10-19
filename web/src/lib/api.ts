import "server-only";

// Server-side API client. The dev bearer token stays on the server; M1 replaces it with the
// signed-in user's session (OIDC) without changing callers.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

export type ApiErrorBody = {
  error: { code: string; message: string; field_errors: Record<string, string[]>; retryable: boolean };
  trace_id: string;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ApiErrorBody | null,
  ) {
    super(body?.error.message ?? `API ${status}`);
  }
}

export type Health = {
  status: string;
  env: string;
  modes: { call_provider: string; connector_mode: string; notify_provider: string; outbound_enabled: boolean };
};

export type Contact = {
  id: string;
  name: string;
  phone_raw: string;
  normalized_phone: string | null;
  phone_status: "valid" | "invalid" | "uncertain";
  lifecycle: string;
  need: string | null;
  version: number;
  created_at: string;
};

export type Page<T> = { items: T[]; next_cursor: string | null; trace_id: string };

async function request<T>(path: string, auth = true): Promise<T> {
  const headers: Record<string, string> = { accept: "application/json" };
  const token = process.env.DEV_AUTH_TOKEN;
  if (auth && token) headers.authorization = `Bearer ${token}`;
  const res = await fetch(`${API_ORIGIN}/api/v1${path}`, { headers, cache: "no-store" });
  if (!res.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await res.json()) as ApiErrorBody;
    } catch {}
    throw new ApiError(res.status, body);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/health", false),
  contacts: (cursor?: string) =>
    request<Page<Contact>>(`/contacts?limit=25${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
};
