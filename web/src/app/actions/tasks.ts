"use server";

import { refresh } from "next/cache";

import { api, ApiError, type TaskPatch, type TaskStatus, type TaskType } from "@/lib/api";

export type TaskFormState = { ok: boolean; message?: string; fieldErrors?: Record<string, string> };

function fromError(e: unknown): TaskFormState {
  if (e instanceof ApiError) {
    const fields = Object.fromEntries(
      Object.entries(e.body?.error.field_errors ?? {}).map(([k, v]) => [k, v.join(", ")]),
    );
    const byCode: Record<string, string> = {
      VERSION_CONFLICT: "Công việc vừa được người khác cập nhật. Đóng và mở lại để xem bản mới.",
      NOT_TASK_OWNER: "Công việc đang do người khác phụ trách.",
      INVALID_TRANSITION: "Công việc đã đóng, không thể đổi trạng thái.",
      TASK_RULES: "Chưa đủ điều kiện cập nhật.",
    };
    return { ok: false, message: byCode[e.code] ?? e.message, fieldErrors: fields };
  }
  return { ok: false, message: "Không kết nối được máy chủ, thử lại sau." };
}

/** datetime-local value is Vietnam wall time; send an explicit offset so the server stores the right UTC. */
function vnLocalToIso(value: string): string | undefined {
  return value ? `${value}:00+07:00` : undefined;
}

export async function updateTaskAction(_prev: TaskFormState, form: FormData): Promise<TaskFormState> {
  const id = String(form.get("id"));
  const version = Number(form.get("version"));
  const patch: TaskPatch = {};
  const owner = String(form.get("owner_id") ?? "");
  if (owner !== String(form.get("orig_owner_id") ?? "")) patch.owner_id = owner || null;
  const status = String(form.get("status") ?? "") as TaskStatus;
  if (status && status !== form.get("orig_status")) patch.status = status;
  const note = String(form.get("resolution_note") ?? "").trim();
  if (note !== String(form.get("orig_note") ?? "")) patch.resolution_note = note || null;
  if (!Object.keys(patch).length) return { ok: false, message: "Chưa có thay đổi nào." };
  try {
    await api.updateTask(id, version, patch);
    refresh();
    return { ok: true };
  } catch (e) {
    return fromError(e);
  }
}

export async function createTaskAction(_prev: TaskFormState, form: FormData): Promise<TaskFormState> {
  const title = String(form.get("title") ?? "").trim();
  if (!title) return { ok: false, fieldErrors: { title: "Nhập nội dung công việc" } };
  const opt = (k: string) => String(form.get(k) ?? "") || undefined;
  try {
    await api.createTask(
      {
        title,
        type: (opt("type") ?? "follow_up") as TaskType,
        priority: opt("priority") === "high" ? "high" : "normal",
        due_at: vnLocalToIso(String(form.get("due_at") ?? "")),
        contact_id: opt("contact_id"),
        call_id: opt("call_id"),
        owner_id: opt("owner_id"),
      },
      String(form.get("idempotency_key")),
    );
    refresh();
    return { ok: true };
  } catch (e) {
    return fromError(e);
  }
}
