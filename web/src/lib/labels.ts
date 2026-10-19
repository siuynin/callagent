import type { Tone } from "@/components/ui/primitives";
import type { Me, TaskStatus, TaskType } from "@/lib/api";

// Vietnamese labels shared by server and client components (keep out of "use client" modules).

export const TASK_STATUS: Record<TaskStatus, { label: string; tone: Tone }> = {
  new: { label: "Mới", tone: "neutral" },
  in_progress: { label: "Đang xử lý", tone: "amber" },
  resolved: { label: "Hoàn thành", tone: "green" },
  cancelled: { label: "Đã hủy", tone: "neutral" },
};

export const TASK_TYPE: Record<TaskType, string> = {
  missed_call: "Cuộc gọi nhỡ",
  human_request: "Yêu cầu người thật",
  callback: "Gọi lại theo yêu cầu",
  appointment_confirm: "Lịch hẹn chờ xác nhận",
  follow_up: "Theo dõi",
};

export const PRIORITY: Record<"high" | "normal", { label: string; tone: Tone }> = {
  high: { label: "Cao", tone: "red" },
  normal: { label: "Thường", tone: "neutral" },
};

export const CALL_OUTCOME: Record<string, { label: string; tone: Tone }> = {
  booked: { label: "Đặt lịch", tone: "green" },
  interested: { label: "Quan tâm", tone: "green" },
  handoff: { label: "Chuyển nhân viên", tone: "amber" },
  callback: { label: "Hẹn gọi lại", tone: "amber" },
  declined: { label: "Từ chối", tone: "red" },
};

export const CALL_STATUS: Record<string, string> = {
  ended: "Đã kết thúc",
  missed: "Cuộc gọi nhỡ",
  failed: "Lỗi",
  created: "Mới tạo",
};

export function outcomeOf(outcome: string | null, status: string): { label: string; tone: Tone } {
  if (outcome && CALL_OUTCOME[outcome]) return CALL_OUTCOME[outcome];
  if (status === "missed") return { label: "Cuộc gọi nhỡ", tone: "red" };
  return { label: outcome ?? CALL_STATUS[status] ?? status, tone: "neutral" };
}

export function mmss(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** Deadline label relative to a fixed "now" passed from the server (avoids hydration mismatch). */
export function dueLabel(dueAt: string | null, overdue: boolean, nowIso: string): string {
  if (!dueAt) return "Không có hạn";
  const due = new Date(dueAt);
  const now = new Date(nowIso);
  const minutes = Math.round((due.getTime() - now.getTime()) / 60000);
  const time = due.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Ho_Chi_Minh" });
  if (overdue) {
    const late = -minutes;
    return late < 60 ? `Quá hạn ${late} phút` : late < 1440 ? `Quá hạn ${Math.round(late / 60)} giờ` : `Quá hạn ${Math.round(late / 1440)} ngày`;
  }
  const day = (d: Date) => d.toLocaleDateString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
  if (day(due) === day(now)) return `Hôm nay · ${time}`;
  const tomorrow = new Date(now.getTime() + 86400000);
  if (day(due) === day(tomorrow)) return `Ngày mai · ${time}`;
  return `${day(due)} · ${time}`;
}

export const ROLE_LABEL: Record<Me["role"], string> = {
  owner: "Chủ sở hữu",
  admin: "Quản trị viên",
  manager: "Quản lý",
  staff: "Nhân viên",
  auditor: "Kiểm soát",
};
