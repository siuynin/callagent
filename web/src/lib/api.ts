import "server-only";

import { getSession, oidcEnabled } from "@/lib/session";

// Server-side API client. Sends the signed-in user's OIDC ID token from the encrypted session cookie
// (ADR 0008); DEV_AUTH_TOKEN is only used when OIDC is not configured. Tokens never reach the browser.
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
  description: string | null;
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
export type Window = [string, string];
export type CalendarException = {
  id: string;
  date_from: string;
  date_to: string;
  kind: "holiday" | "closed" | "special_hours";
  hours: Window[];
  label: string;
};
export type BusinessCalendar = {
  id: string;
  name: string;
  timezone: string;
  weekly_hours: Record<string, Window[]>;
  version: number;
  exceptions: CalendarException[];
  status: { open: boolean; closes_at: string | null; opens_at: string | null; reason: string };
};
export type RouteTarget = "agent" | "announcement";
export type InboundRoute = {
  id: string;
  number: string;
  calendar_id: string;
  in_hours_target: RouteTarget;
  after_hours_target: RouteTarget;
  ai_failure_target: "announcement";
  after_hours_owner: { user_id: string; name: string } | null;
  announcement: string;
  version: number;
};
export type AdminMember = Member & {
  email: string;
  status: "active" | "invited";
  last_login_at: string | null;
  invited_at: string;
};

export type TaskPatch = Partial<{
  owner_id: string | null;
  status: TaskStatus;
  priority: "high" | "normal";
  due_at: string | null;
  outcome: string | null;
  resolution_note: string | null;
}>;

export type AgentConfig = {
  instructions: string;
  greeting: string;
  business_name: string;
  provider: "openai" | "gemini";
  voice: string;
  tools: ("check_available_slots" | "create_appointment" | "request_handoff")[];
  vad_silence_ms: number;
  eval_max_p95_ms: number;
};

export type AgentEval = {
  status: "running" | "finished" | "stale" | null;
  passed: boolean | null;
  valid_for_current_config: boolean;
  summary: {
    scenarios?: number;
    passed?: number;
    failed?: string[];
    false_confirmations?: number;
    worst_p95_ms?: number | null;
    max_p95_ms?: number;
    provider?: string;
    duration_s?: number;
    note?: string;
    checks?: Record<string, { check: string; passed: boolean; got?: unknown }[]>;
    errors?: Record<string, string>;
  } | null;
  requested_at: string | null;
  finished_at: string | null;
  rolled_back_from: number | null;
  error: string | null;
};

export type AgentVersion = {
  id: string;
  number: number;
  status: "draft" | "published" | "retired";
  active: boolean;
  published_at: string | null;
  created_at: string;
  eval: AgentEval | null;
};

export type Agent = {
  id: string;
  name: string;
  purpose: string;
  description: string | null;
  version: number;
  active_version: AgentVersion | null;
  draft: AgentVersion | null;
  provider: string | null;
  calls_today: number;
  versions?: AgentVersion[];
  active_config?: AgentConfig | null;
  draft_config?: AgentConfig | null;
};

export type Page<T> = { items: T[]; next_cursor: string | null; trace_id: string };

type Options = { method?: string; body?: unknown; headers?: Record<string, string>; auth?: boolean };

async function request<T>(path: string, { method = "GET", body, headers = {}, auth = true }: Options = {}): Promise<T> {
  const h: Record<string, string> = { accept: "application/json", ...headers };
  if (auth) {
    const token = oidcEnabled() ? (await getSession())?.idToken : process.env.DEV_AUTH_TOKEN;
    if (token) h.authorization = `Bearer ${token}`;
  }
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
  calendars: () => request<{ items: BusinessCalendar[] }>("/business-calendars"),
  updateCalendar: (id: string, version: number, body: Pick<BusinessCalendar, "name" | "timezone" | "weekly_hours">) =>
    request<{ data: BusinessCalendar }>(`/business-calendars/${encodeURIComponent(id)}`, {
      method: "PUT",
      body,
      headers: { "if-match": String(version) },
    }),
  addCalendarException: (id: string, body: Omit<CalendarException, "id">) =>
    request<{ data: CalendarException }>(`/business-calendars/${encodeURIComponent(id)}/exceptions`, { method: "POST", body }),
  deleteCalendarException: (id: string, exceptionId: string) =>
    request<{ deleted: boolean }>(
      `/business-calendars/${encodeURIComponent(id)}/exceptions/${encodeURIComponent(exceptionId)}`,
      { method: "DELETE" },
    ),
  inboundRoutes: () => request<{ items: InboundRoute[] }>("/inbound-routes"),
  updateRoute: (
    id: string,
    version: number,
    body: { in_hours_target: RouteTarget; after_hours_target: RouteTarget; after_hours_owner_id: string | null; announcement: string },
  ) =>
    request<{ data: InboundRoute }>(`/inbound-routes/${encodeURIComponent(id)}`, {
      method: "PUT",
      body,
      headers: { "if-match": String(version) },
    }),
  adminMembers: () => request<{ items: AdminMember[] }>("/admin/members"),
  inviteMember: (body: { email: string; display_name: string; role: Me["role"] }) =>
    request<{ data: AdminMember }>("/admin/members", { method: "POST", body }),
  changeRole: (userId: string, role: Me["role"]) =>
    request<{ data: AdminMember }>(`/admin/members/${encodeURIComponent(userId)}`, { method: "PATCH", body: { role } }),
  removeMember: (userId: string) =>
    request<{ removed: boolean; released_tasks: number }>(`/admin/members/${encodeURIComponent(userId)}`, { method: "DELETE" }),
  agents: () => request<{ items: Agent[] }>("/agents"),
  agent: (id: string) => request<{ data: Agent }>(`/agents/${encodeURIComponent(id)}`),
  createAgent: (body: { name: string; description?: string }) =>
    request<{ data: Agent }>("/agents", { method: "POST", body }),
  saveDraft: (id: string, agentVersion: number, config: AgentConfig) =>
    request<{ data: Agent }>(`/agents/${encodeURIComponent(id)}/draft`, {
      method: "PUT",
      body: { config },
      headers: { "if-match": String(agentVersion) },
    }),
  runEval: (id: string) => request<{ data: AgentVersion }>(`/agents/${encodeURIComponent(id)}/draft/eval`, { method: "POST" }),
  publish: (id: string, versionId: string) =>
    request<{ data: Agent }>(`/agents/${encodeURIComponent(id)}/publish`, { method: "POST", body: { version_id: versionId } }),
  rollback: (id: string, versionId: string) =>
    request<{ data: Agent }>(`/agents/${encodeURIComponent(id)}/rollback`, { method: "POST", body: { version_id: versionId } }),
};

