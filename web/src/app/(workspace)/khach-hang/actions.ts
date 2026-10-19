"use server";

import { refresh } from "next/cache";

import { api, ApiError } from "@/lib/api";

export type FormState = {
  ok: boolean;
  message?: string;
  fieldErrors?: Record<string, string>;
  phoneWarning?: string;
};

const PHONE_REASON: Record<string, string> = {
  bad_length_or_prefix: "Số điện thoại sai định dạng, đã lưu và đánh dấu Sai số.",
  missing_prefix_needs_review: "Số thiếu số 0 đầu, đã lưu và đánh dấu Cần kiểm tra.",
  non_vn_country_code: "Không phải số Việt Nam, đã lưu và đánh dấu Sai số.",
};

function apiMessage(e: unknown): FormState {
  if (e instanceof ApiError) {
    if (e.code === "VERSION_CONFLICT") {
      return { ok: false, message: "Hồ sơ vừa được người khác cập nhật. Tải lại trang để xem bản mới rồi sửa tiếp." };
    }
    if (e.status === 401 || e.status === 403) return { ok: false, message: "Bạn không có quyền thực hiện thao tác này." };
    const fields = Object.fromEntries(
      Object.entries(e.body?.error.field_errors ?? {}).map(([k, v]) => [k, v.join(", ")]),
    );
    return { ok: false, message: e.message, fieldErrors: fields };
  }
  return { ok: false, message: "Không kết nối được máy chủ, thử lại sau." };
}

export async function createContactAction(_prev: FormState, form: FormData): Promise<FormState> {
  const name = String(form.get("name") ?? "").trim();
  const phone = String(form.get("phone") ?? "").trim();
  const need = String(form.get("need") ?? "").trim();
  // generated once per open modal: a double submit or a retried request returns the same contact
  const key = String(form.get("idempotency_key") ?? "");
  const fieldErrors: Record<string, string> = {};
  if (!name) fieldErrors.name = "Nhập tên khách hàng";
  if (!phone) fieldErrors.phone = "Nhập số điện thoại";
  if (Object.keys(fieldErrors).length) return { ok: false, fieldErrors };
  try {
    const res = await api.createContact({ name, phone, ...(need ? { need } : {}) }, key);
    refresh();
    const reason = res.phone_check.reason;
    return { ok: true, phoneWarning: reason ? (PHONE_REASON[reason] ?? "Số điện thoại cần kiểm tra lại.") : undefined };
  } catch (e) {
    return apiMessage(e);
  }
}

export async function updateContactAction(_prev: FormState, form: FormData): Promise<FormState> {
  const id = String(form.get("id") ?? "");
  const version = Number(form.get("version"));
  const name = String(form.get("name") ?? "").trim();
  const need = String(form.get("need") ?? "").trim();
  if (!name) return { ok: false, fieldErrors: { name: "Nhập tên khách hàng" } };
  try {
    await api.updateContact(id, version, { name, need: need || null });
    refresh();
    return { ok: true };
  } catch (e) {
    return apiMessage(e);
  }
}
