"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";

import { type AgentConfig, api, ApiError } from "@/lib/api";

export type AgentActionState = { ok: boolean; message?: string; fieldErrors?: Record<string, string>; at?: number };

function fail(e: unknown): AgentActionState {
  if (e instanceof ApiError) {
    const fields = Object.fromEntries(
      Object.entries(e.body?.error.field_errors ?? {}).map(([k, v]) => [k.split(".")[0], v.join(" · ")]),
    );
    const byCode: Record<string, string> = {
      VERSION_CONFLICT: "Agent vừa được người khác chỉnh sửa. Tải lại trang để xem bản mới.",
      EVAL_REQUIRED: "Bản nháp phải đạt bộ đánh giá voice trước khi xuất bản.",
      EVAL_RUNNING: "Đánh giá đang chạy, đợi kết quả rồi thử lại.",
      GATEWAY_UNAVAILABLE: "Không gọi được media gateway để chạy đánh giá. Kiểm tra gateway đang chạy.",
      GATEWAY_NOT_CONFIGURED: "Chưa cấu hình kết nối backend ↔ gateway (GATEWAY_SERVICE_TOKEN).",
      FORBIDDEN: "Vai trò hiện tại không đủ quyền.",
    };
    return { ok: false, message: byCode[e.code] ?? e.message, fieldErrors: fields, at: Date.now() };
  }
  return { ok: false, message: "Không kết nối được máy chủ, thử lại sau.", at: Date.now() };
}

export async function saveDraftAction(_prev: AgentActionState, form: FormData): Promise<AgentActionState> {
  const id = String(form.get("agent_id"));
  const version = Number(form.get("agent_version"));
  let config: AgentConfig;
  try {
    config = JSON.parse(String(form.get("config")));
  } catch {
    return { ok: false, message: "Cấu hình không đọc được.", at: Date.now() };
  }
  try {
    await api.saveDraft(id, version, config);
    refresh();
    return { ok: true, message: "Đã lưu bản nháp. Chạy đánh giá trước khi xuất bản.", at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}

export async function runEvalAction(_prev: AgentActionState, form: FormData): Promise<AgentActionState> {
  try {
    await api.runEval(String(form.get("agent_id")));
    refresh();
    return { ok: true, message: "Đã gửi yêu cầu đánh giá. Kết quả có sau vài phút.", at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}

export async function publishAction(_prev: AgentActionState, form: FormData): Promise<AgentActionState> {
  try {
    await api.publish(String(form.get("agent_id")), String(form.get("version_id")));
    refresh();
    return { ok: true, message: "Đã xuất bản. Cuộc gọi mới dùng phiên bản này.", at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}

export async function rollbackAction(_prev: AgentActionState, form: FormData): Promise<AgentActionState> {
  try {
    await api.rollback(String(form.get("agent_id")), String(form.get("version_id")));
    refresh();
    return { ok: true, message: "Đã quay lại phiên bản cũ (tạo phiên bản mới từ bản đó).", at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}

export async function createAgentAction(_prev: AgentActionState, form: FormData): Promise<AgentActionState> {
  const name = String(form.get("name") ?? "").trim();
  if (!name) return { ok: false, fieldErrors: { name: "Nhập tên agent" }, at: Date.now() };
  let id: string;
  try {
    const description = String(form.get("description") ?? "").trim();
    id = (await api.createAgent({ name, ...(description ? { description } : {}) })).data.id;
  } catch (e) {
    return fail(e);
  }
  redirect(`/agents/${id}`);
}
