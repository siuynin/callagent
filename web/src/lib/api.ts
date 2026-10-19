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
  get code() {
    return this.body?.error.code ?? "UNKNOWN";
  }
}

export type Health = {
  status: string;
  env: string;
  modes: { call_provider: string; connector_mode: string; notify_provider: string; outbound_enabled: boolean };
};

export type Me = {
  user_id: string;
  display_name: string;
  role: "owner" | "admin" | "manager" | "staff" | "auditor";
  tenant: { id: string; name: string; timezone: string };
};

export type Contact = {
  id: string;
  name: string;
  phone_raw: string;
  normalized_phone: string | null;
  phone_status: "valid" | "invalid" | "uncertain";
  owner_id: string | null;
  lifecycle: string;
  need: string | null;
  optout_at: string | null;
  version: number;
  created_at: string;
};

export type Call = {
  id: string;
  direction: "inbound" | "outbound";
  contact_id: string | null;
  started_at: string;
  ended_at: string | null;
  technical_status: string;
  business_outcome: string | null;
};

export type Page<T> = { items: T[]; next_cursor: string | null; trace_id: string };

type Options = { method?: string; body?: unknown; headers?: Record<string, string>; auth?: boolean };

async function request<T>(path: string, { method = "GET", body, headers = {}, auth = true }: Options = {}): Promise<T> {
  const h: Record<string, string> = { accept: "application/json", ...headers };
  const token = process.env.DEV_AUTH_TOKEN;
  if (auth && token) h.authorization = `Bearer ${token}`;
  if (body !== undefined) h["content-type"] = "application/json";
  const res = await fetch(`${API_ORIGIN}/api/v1${path}`, {
    method,
    headers: h,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    let parsed: ApiErrorBody | null = null;
    try {
      parsed = (await res.json()) as ApiErrorBody;
    } catch {}
    throw new ApiError(res.status, parsed);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/health", { auth: false }),
  me: () => request<Me>("/me"),
  contacts: (cursor?: string) =>
    request<Page<Contact>>(`/contacts?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`),
  contact: (id: string) => request<{ data: Contact }>(`/contacts/${encodeURIComponent(id)}`),
  createContact: (body: { name: string; phone: string; need?: string }, idempotencyKey: string) =>
    request<{ data: Contact; phone_check: { status: string; reason: string | null } }>("/contacts", {
      method: "POST",
      body,
      headers: { "idempotency-key": idempotencyKey },
    }),
  updateContact: (id: string, version: number, body: { name?: string; need?: string | null }) =>
    request<{ data: Contact }>(`/contacts/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body,
      headers: { "if-match": String(version) },
    }),
  calls: () => request<Page<Call>>("/calls?limit=5"),
};

export const ROLE_LABEL: Record<Me["role"], string> = {
  owner: "Chủ sở hữu",
  admin: "Quản trị viên",
  manager: "Quản lý",
  staff: "Nhân viên",
  auditor: "Kiểm soát",
};
