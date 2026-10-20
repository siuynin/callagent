"use server";

import { refresh } from "next/cache";

import { api, ApiError, type CalendarException, type RouteTarget, type Window } from "@/lib/api";

export type CalendarState = { ok: boolean; message?: string; fieldErrors?: Record<string, string>; at?: number };

function fail(e: unknown): CalendarState {
  if (e instanceof ApiError) {
    const fields = Object.fromEntries(
      Object.entries(e.body?.error.field_errors ?? {}).map(([k, v]) => [k, v.join(" · ")]),
    );
    const byCode: Record<string, string> = {
      VERSION_CONFLICT: "Người khác vừa sửa mục này. Tải lại trang để xem bản mới.",
      FORBIDDEN: "Chỉ quản trị viên mới sửa được lịch làm việc và định tuyến.",
    };
    return { ok: false, message: byCode[e.code] ?? e.message, fieldErrors: fields, at: Date.now() };
  }
  return { ok: false, message: "Không kết nối được máy chủ, thử lại sau.", at: Date.now() };
}

export async function saveHoursAction(_prev: CalendarState, form: FormData): Promise<CalendarState> {
  let weekly: Record<string, Window[]>;
  try {
    weekly = JSON.parse(String(form.get("weekly_hours")));
  } catch {
    return { ok: false, message: "Giờ làm việc không đọc được.", at: Date.now() };
  }
  try {
    await api.updateCalendar(String(form.get("calendar_id")), Number(form.get("version")), {
      name: String(form.get("name")),
      timezone: String(form.get("timezone")),
      weekly_hours: weekly,
    });
    refresh();
    return { ok: true, message: "Đã lưu giờ làm việc.", at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}

export async function addExceptionAction(_prev: CalendarState, form: FormData): Promise<CalendarState> {
  const kind = String(form.get("kind")) as CalendarException["kind"];
  const dateFrom = String(form.get("date_from") ?? "");
  const errors: Record<string, string> = {};
  if (!dateFrom) errors.date_from = "Chọn ngày bắt đầu";
  if (!String(form.get("label") ?? "").trim()) errors.label = "Nhập tên ngày nghỉ";
  if (Object.keys(errors).length) return { ok: false, fieldErrors: errors, at: Date.now() };
  const hours: Window[] = kind === "special_hours" ? [[String(form.get("open")), String(form.get("close"))]] : [];
  try {
    await api.addCalendarException(String(form.get("calendar_id")), {
      date_from: dateFrom,
      date_to: String(form.get("date_to") || dateFrom),
      kind,
      hours,
      label: String(form.get("label")).trim(),
    });
    refresh();
    return { ok: true, message: "Đã thêm ngày nghỉ.", at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}

export async function deleteExceptionAction(_prev: CalendarState, form: FormData): Promise<CalendarState> {
  try {
    await api.deleteCalendarException(String(form.get("calendar_id")), String(form.get("exception_id")));
    refresh();
    return { ok: true, message: "Đã xóa ngày nghỉ.", at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}

export async function saveRouteAction(_prev: CalendarState, form: FormData): Promise<CalendarState> {
  try {
    await api.updateRoute(String(form.get("route_id")), Number(form.get("version")), {
      in_hours_target: String(form.get("in_hours_target")) as RouteTarget,
      after_hours_target: String(form.get("after_hours_target")) as RouteTarget,
      after_hours_owner_id: String(form.get("after_hours_owner_id") || "") || null,
      announcement: String(form.get("announcement") ?? ""),
    });
    refresh();
    return { ok: true, message: "Đã lưu định tuyến.", at: Date.now() };
  } catch (e) {
    return fail(e);
  }
}
