"use client";

import { useActionState, useEffect, useMemo, useState } from "react";

import {
  addExceptionAction,
  type CalendarState,
  deleteExceptionAction,
  saveHoursAction,
  saveRouteAction,
} from "@/app/actions/calendar";
import { Modal } from "@/components/ui/Modal";
import { Card, DataTable, Empty, Notice, Pill } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toast";
import type { BusinessCalendar, CalendarException, InboundRoute, Member, RouteTarget, Window } from "@/lib/api";
import { submitTo } from "@/lib/forms";

const DAYS = [
  ["1", "Thứ Hai"],
  ["2", "Thứ Ba"],
  ["3", "Thứ Tư"],
  ["4", "Thứ Năm"],
  ["5", "Thứ Sáu"],
  ["6", "Thứ Bảy"],
  ["7", "Chủ nhật"],
] as const;
const KIND: Record<CalendarException["kind"], { label: string; tone: "red" | "amber" | "neutral" }> = {
  holiday: { label: "Nghỉ lễ", tone: "red" },
  closed: { label: "Đóng cửa", tone: "amber" },
  special_hours: { label: "Giờ đặc biệt", tone: "neutral" },
};
const TARGET: Record<RouteTarget, string> = {
  agent: "AI lễ tân tiếp nhận",
  announcement: "Phát thông báo giờ làm việc",
};
const INITIAL: CalendarState = { ok: false };

function useToastOnSuccess(state: CalendarState) {
  const toast = useToast();
  useEffect(() => {
    if (state.ok && state.message) toast(state.message);
  }, [state, toast]);
}

function when(iso: string | null, tz: string): string {
  if (!iso) return "chưa có khung giờ mở cửa trong năm tới";
  return new Date(iso).toLocaleString("vi-VN", { timeZone: tz, weekday: "long", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" });
}

function dateRange(e: CalendarException): string {
  const fmt = (d: string) => d.split("-").reverse().join("/");
  return e.date_from === e.date_to ? fmt(e.date_from) : `${fmt(e.date_from)} – ${fmt(e.date_to)}`;
}

function StatusBanner({ calendar }: { calendar: BusinessCalendar }) {
  const s = calendar.status;
  if (s.open) {
    return (
      <Notice>
        <Pill tone="green">Đang trong giờ làm việc</Pill> Đóng cửa lúc {when(s.closes_at, calendar.timezone)}. Cuộc gọi đến lúc này đi theo định tuyến trong giờ.
      </Notice>
    );
  }
  const why = s.reason === "outside_hours" ? "Ngoài giờ làm việc" : `Nghỉ: ${s.reason}`;
  return (
    <Notice tone="warn">
      <Pill tone="amber">{why}</Pill> Mở lại {when(s.opens_at, calendar.timezone)}. Cuộc gọi đến lúc này đi theo định tuyến ngoài giờ.
    </Notice>
  );
}

function HoursCard({ calendar, canEdit }: { calendar: BusinessCalendar; canEdit: boolean }) {
  const [state, action, pending] = useActionState(saveHoursAction, INITIAL);
  const [weekly, setWeekly] = useState<Record<string, Window[]>>(calendar.weekly_hours);
  useToastOnSuccess(state);
  const dirty = JSON.stringify(weekly) !== JSON.stringify(calendar.weekly_hours);
  const set = (day: string, windows: Window[]) => setWeekly((w) => ({ ...w, [day]: windows }));
  return (
    <Card
      title="Giờ làm việc trong tuần"
      action={<span className="small">Múi giờ {calendar.timezone}</span>}
    >
      <form className="pad" onSubmit={submitTo(action)}>
        <input type="hidden" name="calendar_id" value={calendar.id} />
        <input type="hidden" name="version" value={calendar.version} />
        <input type="hidden" name="name" value={calendar.name} />
        <input type="hidden" name="timezone" value={calendar.timezone} />
        <input type="hidden" name="weekly_hours" value={JSON.stringify(weekly)} />
        {DAYS.map(([key, label]) => {
          const windows = weekly[key] ?? [];
          const open = windows.length > 0;
          return (
            <div className="hoursrow" key={key}>
              <b>{label}</b>
              <label className="small" style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={open}
                  disabled={!canEdit}
                  onChange={(e) => set(key, e.target.checked ? [["08:00", "17:30"]] : [])}
                  aria-label={`${label} mở cửa`}
                />
                {open ? "Mở" : "Nghỉ"}
              </label>
              <div className="windows">
                {windows.map((w, i) => (
                  <span className="window" key={i}>
                    <input
                      type="time"
                      value={w[0]}
                      disabled={!canEdit}
                      aria-label={`${label} mở cửa lúc`}
                      onChange={(e) => set(key, windows.map((x, j) => (j === i ? [e.target.value, x[1]] : x)))}
                    />
                    –
                    <input
                      type="time"
                      value={w[1] === "24:00" ? "23:59" : w[1]}
                      disabled={!canEdit}
                      aria-label={`${label} đóng cửa lúc`}
                      onChange={(e) => set(key, windows.map((x, j) => (j === i ? [x[0], e.target.value] : x)))}
                    />
                    {canEdit && windows.length > 1 && (
                      <button type="button" className="flat" aria-label="Bỏ khung giờ này" onClick={() => set(key, windows.filter((_, j) => j !== i))}>
                        ✕
                      </button>
                    )}
                  </span>
                ))}
                {canEdit && open && windows.length < 3 && (
                  <button type="button" className="flat" onClick={() => set(key, [...windows, ["13:30", "17:30"]])}>
                    + Khung giờ
                  </button>
                )}
              </div>
            </div>
          );
        })}
        {state.message && !state.ok && (
          <div className="fielderror" role="alert">
            {state.message}
          </div>
        )}
        {canEdit && (
          <div className="actions" style={{ marginTop: 14 }}>
            <button type="submit" className="primary" disabled={pending || !dirty}>
              {pending ? "Đang lưu…" : "Lưu giờ làm việc"}
            </button>
            {dirty && (
              <button type="button" onClick={() => setWeekly(calendar.weekly_hours)}>
                Hoàn tác
              </button>
            )}
          </div>
        )}
      </form>
    </Card>
  );
}

function DeleteException({ calendarId, e }: { calendarId: string; e: CalendarException }) {
  const [state, action, pending] = useActionState(deleteExceptionAction, INITIAL);
  useToastOnSuccess(state);
  return (
    <form onSubmit={submitTo(action)}>
      <input type="hidden" name="calendar_id" value={calendarId} />
      <input type="hidden" name="exception_id" value={e.id} />
      <button type="submit" className="flat" style={{ color: "#b06464" }} disabled={pending} aria-label={`Xóa ${e.label}`}>
        Xóa
      </button>
      {!state.ok && state.message && <span className="fielderror">{state.message}</span>}
    </form>
  );
}

function AddExceptionModal({ calendarId, onClose }: { calendarId: string; onClose: () => void }) {
  const [state, action, pending] = useActionState(addExceptionAction, INITIAL);
  const [v, setV] = useState({ date_from: "", date_to: "", kind: "holiday", label: "", open: "08:00", close: "12:00" });
  const toast = useToast();
  useEffect(() => {
    if (state.ok) {
      toast(state.message ?? "Đã thêm");
      onClose();
    }
  }, [state, toast, onClose]);
  const bind = (k: keyof typeof v) => ({
    name: k,
    value: v[k],
    onChange: (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value })),
  });
  return (
    <Modal
      title="Thêm ngày nghỉ hoặc giờ đặc biệt"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose}>
            Hủy
          </button>
          <button type="submit" form="add-exception" className="primary" disabled={pending}>
            {pending ? "Đang lưu…" : "Thêm"}
          </button>
        </>
      }
    >
      <form id="add-exception" onSubmit={submitTo(action)} noValidate>
        <input type="hidden" name="calendar_id" value={calendarId} />
        <div className="field">
          <label htmlFor="x-label">Tên *</label>
          <input id="x-label" placeholder="Ví dụ: Tết Nguyên đán 2027" {...bind("label")} />
          {state.fieldErrors?.label && <div className="fielderror">{state.fieldErrors.label}</div>}
        </div>
        <div className="field">
          <label htmlFor="x-kind">Loại</label>
          <select id="x-kind" {...bind("kind")}>
            <option value="holiday">Nghỉ lễ (đóng cả ngày)</option>
            <option value="closed">Đóng cửa (sự kiện nội bộ, kiểm kê…)</option>
            <option value="special_hours">Giờ đặc biệt (thay giờ thường)</option>
          </select>
        </div>
        <div className="formgrid">
          <div className="field">
            <label htmlFor="x-from">Từ ngày *</label>
            <input id="x-from" type="date" {...bind("date_from")} />
            {state.fieldErrors?.date_from && <div className="fielderror">{state.fieldErrors.date_from}</div>}
          </div>
          <div className="field">
            <label htmlFor="x-to">Đến ngày</label>
            <input id="x-to" type="date" min={v.date_from || undefined} {...bind("date_to")} />
            {state.fieldErrors?.date_to && <div className="fielderror">{state.fieldErrors.date_to}</div>}
          </div>
        </div>
        {v.kind === "special_hours" && (
          <div className="formgrid">
            <div className="field">
              <label htmlFor="x-open">Mở cửa</label>
              <input id="x-open" type="time" {...bind("open")} />
            </div>
            <div className="field">
              <label htmlFor="x-close">Đóng cửa</label>
              <input id="x-close" type="time" {...bind("close")} />
            </div>
            {state.fieldErrors?.hours && <div className="fielderror full">{state.fieldErrors.hours}</div>}
          </div>
        )}
        <p className="small">Tết và Giỗ Tổ theo âm lịch, ngày nghỉ bù thay đổi mỗi năm: nhập theo thông báo chính thức.</p>
        {state.message && !state.ok && (
          <div className="fielderror" role="alert">
            {state.message}
          </div>
        )}
      </form>
    </Modal>
  );
}

function ExceptionsCard({ calendar, canEdit }: { calendar: BusinessCalendar; canEdit: boolean }) {
  const [adding, setAdding] = useState(false);
  const [showPast, setShowPast] = useState(false);
  const today = useMemo(
    () => new Date().toLocaleDateString("sv-SE", { timeZone: calendar.timezone }),
    [calendar.timezone],
  );
  const past = calendar.exceptions.filter((e) => e.date_to < today);
  const shown = showPast ? calendar.exceptions : calendar.exceptions.filter((e) => e.date_to >= today);
  const samples = calendar.exceptions.some((e) => e.label.includes("(mẫu"));
  return (
    <Card
      title="Ngày nghỉ & giờ đặc biệt"
      action={
        canEdit && (
          <button type="button" className="primary" onClick={() => setAdding(true)}>
            + Thêm ngày
          </button>
        )
      }
    >
      {samples && (
        <div className="pad" style={{ paddingBottom: 0 }}>
          <Notice tone="warn">Có ngày nghỉ mẫu do hệ thống tạo. Đối chiếu với thông báo nghỉ lễ chính thức rồi sửa hoặc xóa.</Notice>
        </div>
      )}
      {shown.length === 0 ? (
        <div className="pad">
          <Empty>Chưa có ngày nghỉ sắp tới. Thêm Tết và các ngày lễ để AI không hẹn khách vào ngày đóng cửa.</Empty>
        </div>
      ) : (
        <DataTable heads={["Ngày", "Loại", "Tên", "Giờ", ""]}>
          {shown.map((e) => (
            <tr key={e.id} style={e.date_to < today ? { opacity: 0.55 } : undefined}>
              <td>
                <strong>{dateRange(e)}</strong>
              </td>
              <td>
                <Pill tone={KIND[e.kind].tone}>{KIND[e.kind].label}</Pill>
              </td>
              <td style={{ whiteSpace: "normal" }}>{e.label}</td>
              <td>{e.kind === "special_hours" ? e.hours.map((w) => w.join("–")).join(", ") : "Đóng cả ngày"}</td>
              <td>{canEdit && <DeleteException calendarId={calendar.id} e={e} />}</td>
            </tr>
          ))}
        </DataTable>
      )}
      {past.length > 0 && (
        <div className="foot">
          <span>{past.length} ngày đã qua</span>
          <button type="button" className="flat" onClick={() => setShowPast((x) => !x)}>
            {showPast ? "Ẩn ngày đã qua" : "Hiện ngày đã qua"}
          </button>
        </div>
      )}
      {adding && <AddExceptionModal calendarId={calendar.id} onClose={() => setAdding(false)} />}
    </Card>
  );
}

function RouteCard({ route, owners, canEdit }: { route: InboundRoute; owners: Member[]; canEdit: boolean }) {
  const [state, action, pending] = useActionState(saveRouteAction, INITIAL);
  const initial = {
    in_hours_target: route.in_hours_target,
    after_hours_target: route.after_hours_target,
    after_hours_owner_id: route.after_hours_owner?.user_id ?? "",
    announcement: route.announcement,
  };
  const [v, setV] = useState(initial);
  useToastOnSuccess(state);
  const dirty = JSON.stringify(v) !== JSON.stringify(initial);
  const bind = (k: keyof typeof v) => ({
    name: k,
    value: v[k],
    disabled: !canEdit,
    onChange: (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value })),
  });
  return (
    <Card title="Định tuyến cuộc gọi đến" action={<span className="small">Mọi số của workspace</span>}>
      <form className="pad" onSubmit={submitTo(action)}>
        <input type="hidden" name="route_id" value={route.id} />
        <input type="hidden" name="version" value={route.version} />
        <div className="field">
          <label htmlFor="r-in">Trong giờ làm việc</label>
          <select id="r-in" {...bind("in_hours_target")}>
            {(Object.keys(TARGET) as RouteTarget[]).map((t) => (
              <option key={t} value={t}>
                {TARGET[t]}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="r-after">Ngoài giờ làm việc</label>
          <select id="r-after" {...bind("after_hours_target")}>
            <option value="agent">AI tiếp nhận & tạo lịch gọi lại</option>
            <option value="announcement">{TARGET.announcement}</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="r-fail">Khi AI gặp lỗi</label>
          <select id="r-fail" disabled value="announcement">
            <option value="announcement">Phát thông báo & ghi yêu cầu gọi lại</option>
          </select>
          <div className="small">Chuyển máy nhánh có khi kết nối tổng đài thật.</div>
        </div>
        <div className="field">
          <label htmlFor="r-owner">Người nhận việc phát sinh ngoài giờ</label>
          <select id="r-owner" {...bind("after_hours_owner_id")}>
            <option value="">Chưa phân công (vào Hộp việc chung)</option>
            {owners.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.name}
              </option>
            ))}
          </select>
          <div className="small">Yêu cầu gặp nhân viên hoặc lịch hẹn tạo ngoài giờ sẽ giao cho người này, hạn trong giờ làm việc kế tiếp.</div>
        </div>
        <div className="field">
          <label htmlFor="r-ann">Nội dung thông báo</label>
          <textarea id="r-ann" rows={3} style={{ minHeight: 80 }} {...bind("announcement")} />
          {state.fieldErrors?.announcement && <div className="fielderror">{state.fieldErrors.announcement}</div>}
          <div className="small">Hệ thống tự thêm lời giới thiệu tự động, câu thông báo ghi âm và giờ mở cửa kế tiếp.</div>
        </div>
        {state.message && !state.ok && (
          <div className="fielderror" role="alert">
            {state.message}
          </div>
        )}
        {canEdit && (
          <button type="submit" className="primary" disabled={pending || !dirty}>
            {pending ? "Đang lưu…" : "Lưu định tuyến"}
          </button>
        )}
      </form>
    </Card>
  );
}

export function CalendarView({
  calendar,
  route,
  owners,
  canEdit,
}: {
  calendar: BusinessCalendar;
  route: InboundRoute;
  owners: Member[];
  canEdit: boolean;
}) {
  return (
    <>
      <StatusBanner calendar={calendar} />
      {!canEdit && <Notice>Bạn đang xem. Chỉ quản trị viên sửa được giờ làm việc và định tuyến.</Notice>}
      <div className="grid cols">
        {/* key: a saved version remounts the editor with the server's values */}
        <HoursCard key={`h${calendar.version}`} calendar={calendar} canEdit={canEdit} />
        <RouteCard key={`r${route.version}`} route={route} owners={owners} canEdit={canEdit} />
      </div>
      <ExceptionsCard calendar={calendar} canEdit={canEdit} />
    </>
  );
}
