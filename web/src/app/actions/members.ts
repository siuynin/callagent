"use server";

import { refresh } from "next/cache";

import { api, ApiError, type Me } from "@/lib/api";

export type MemberState = { ok: boolean; message?: string; fieldErrors?: Record<string, string>; at?: number };

function fail(e: unknown): MemberState {
  if (e instanceof ApiError) {
    const fields = Object.fromEntries(
      Object.entries(e.body?.error.field_errors ?? {}).map(([k, v]) => [k, v.join(" · ")]),
    );
    const byCode: Record<string, string> = {
      ALREADY_MEMBER: "Email này đã là thành viên của workspace.",
      OWNER_ONLY: "Chỉ chủ sở hữu mới thao tác được với quyền chủ sở hữu.",
      LAST_ADMIN: "Workspace cần ít nhất một quản trị viên.",
      SELF_CHANGE: "Không tự đổi vai trò hoặc tự gỡ chính mình.",
      FORBIDDEN: "Vai trò hiện tại không đủ quyền.",
      INVALID_REQUEST: "Email không hợp lệ.",
    };
    return { ok: false, message: byCode[e.code] ?? e.message, fieldErrors: fields, at: Date.now() };
  }
  return { ok: false, message: "Không kết nối được máy chủ, thử lại sau.", at: Date.now() };
}

export async function inviteMemberAction(_prev: MemberState, form: FormData): Promise<MemberState> {
  const email = String(form.get("email") ?? "").trim();
  const name = String(form.get("display_name") ?? "").trim();
  const errors: Record<string, string> = {};
  if (!email) errors.email = "Nhập email";
  if (!name) errors.display_name = "Nhập tên hiển thị";
  if (Object.keys(errors).length) return { ok: false, fieldErrors: errors, at: Date.now() };
  try {
    await api.inviteMember({ email, display_name: name, role: String(form.get("role")) as Me["role"] });
    refresh();
    return { ok: true, message: `Đã mời ${email}. Người được mời đăng nhập bằng đúng email này.`, at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}

export async function changeRoleAction(_prev: MemberState, form: FormData): Promise<MemberState> {
  try {
    await api.changeRole(String(form.get("user_id")), String(form.get("role")) as Me["role"]);
    refresh();
    return { ok: true, message: "Đã đổi vai trò.", at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}

export async function removeMemberAction(_prev: MemberState, form: FormData): Promise<MemberState> {
  try {
    const r = await api.removeMember(String(form.get("user_id")));
    refresh();
    const released = r.released_tasks ? ` ${r.released_tasks} việc đang mở được trả về "chưa phân công".` : "";
    return { ok: true, message: `Đã gỡ khỏi workspace.${released}`, at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}
