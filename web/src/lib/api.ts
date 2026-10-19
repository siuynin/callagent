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
  contact_name: string | null;
  provider: string;
  started_at: string;
  answered_at: string | null;
  ended_at: string | null;
  duration_s: number;
  technical_status: string;
  business_outcome: string | null;
  after_hours: boolean;
};

export type CallDetail = {
  data: Call;
  turns: { seq: number; speaker: "customer" | "agent" | "staff"; text: string; started_ms: number; played_until_ms: number | null }[];
  tool_runs: { seq: number; tool: string; args: Record<string, unknown>; status: string; result: Record<string, unknown> | null; started_ms: number }[];
  tasks: { id: string; type: TaskType; title: string; status: TaskStatus }[];
};

export type TaskType = "missed_call" | "human_request" | "callback" | "appointment_confirm" | "follow_up";
export type TaskStatus = "new" | "in_progress" | "resolved" | "cancelled";

export type Task = {
  id: string;
  type: TaskType;
  title: string;
  contact: { id: string; name: string } | null;
  call_id: string | null;
  owner: { id: string; name: string } | null;
  priority: "high" | "normal";
  due_at: string | null;
  overdue: boolean;
  status: TaskStatus;
  outcome: string | null;
  resolution_note: string | null;
  resolved_at: string | null;
  version: number;
  created_at: string;
};

export type TaskSummary = { unassigned: number; overdue: number; in_progress: number; resolved: number };
export type Member = { user_id: string; name: string; role: Me["role"] };

export type TaskPatch = Partial<{
  owner_id: string | null;
  status: TaskStatus;
  priority: "high" | "normal";
  due_at: string | null;
  outcome: string | null;
  resolution_note: string | null;
}>;

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
  calls: (limit = 5) => request<Page<Call>>(`/calls?limit=${limit}`),
  call: (id: string) => request<CallDetail>(`/calls/${encodeURIComponent(id)}`),
  tasks: () => request<{ items: Task[] }>("/tasks?limit=100"),
  taskSummary: () => request<TaskSummary>("/tasks/summary"),
  createTask: (
    body: { type: TaskType; title: string; contact_id?: string; call_id?: string; priority?: "high" | "normal"; due_at?: string; owner_id?: string },
    idempotencyKey: string,
  ) => request<{ data: Task }>("/tasks", { method: "POST", body, headers: { "idempotency-key": idempotencyKey } }),
  updateTask: (id: string, version: number, body: TaskPatch) =>
    request<{ data: Task }>(`/tasks/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body,
      headers: { "if-match": String(version) },
    }),
  members: () => request<{ items: Member[] }>("/members"),
};

export const ROLE_LABEL: Record<Me["role"], string> = {
  owner: "Chủ sở hữu",
  admin: "Quản trị viên",
  manager: "Quản lý",
  staff: "Nhân viên",
  auditor: "Kiểm soát",
};
