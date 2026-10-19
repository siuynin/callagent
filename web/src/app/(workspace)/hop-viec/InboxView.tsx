"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { CreateTaskModal, ProcessTaskModal } from "@/components/tasks/TaskForms";
import { DataTable, Empty, Pill } from "@/components/ui/primitives";
import type { Member, Task } from "@/lib/api";
import { dueLabel, PRIORITY, TASK_STATUS, TASK_TYPE } from "@/lib/labels";
import { fold } from "@/lib/text";

const TABS = ["Tất cả", "Mới", "Đang xử lý", "Quá hạn", "Hoàn thành"] as const;
type Tab = (typeof TABS)[number];

function matches(t: Task, tab: Tab): boolean {
  switch (tab) {
    case "Mới":
      return t.status === "new";
    case "Đang xử lý":
      return t.status === "in_progress";
    case "Quá hạn":
      return t.overdue;
    case "Hoàn thành":
      return t.status === "resolved";
    default:
      return true;
  }
}

export function InboxView({ tasks, members, now }: { tasks: Task[]; members: Member[]; now: string }) {
  const [tab, setTab] = useState<Tab>("Tất cả");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const rows = useMemo(() => {
    const q = fold(query.trim());
    return tasks.filter(
      (t) => matches(t, tab) && (!q || fold(`${t.title} ${t.contact?.name ?? ""} ${TASK_TYPE[t.type]}`).includes(q)),
    );
  }, [tasks, tab, query]);
  const open = tasks.find((t) => t.id === openId) ?? null;

  return (
    <>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} className={tab === t ? "active" : undefined} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>
      <div className="toolbar">
        <input aria-label="Tìm công việc" placeholder="Tìm khách hoặc loại yêu cầu…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <span className="small">{rows.length} yêu cầu</span>
        <div className="right">
          <button type="button" className="primary" onClick={() => setCreating(true)}>
            + Tạo công việc
          </button>
        </div>
      </div>
      <section className="card">
        <div className="cardhead">
          <h2>Yêu cầu cần tiếp nhận</h2>
        </div>
        {rows.length === 0 ? (
          <div className="pad">
            <Empty>Không có yêu cầu phù hợp bộ lọc.</Empty>
          </div>
        ) : (
          <>
            <DataTable heads={["Khách / yêu cầu", "Ưu tiên", "Hạn xử lý", "Phụ trách", "Trạng thái", ""]} responsive>
              {rows.map((t) => (
                <tr key={t.id}>
                  <td>
                    <button type="button" className="flat link" style={{ padding: 0 }} onClick={() => setOpenId(t.id)}>
                      {t.contact?.name ?? t.title}
                    </button>
                    <small>
                      {TASK_TYPE[t.type]} · {t.title}
                    </small>
                  </td>
                  <td>
                    <Pill tone={PRIORITY[t.priority].tone}>{PRIORITY[t.priority].label}</Pill>
                  </td>
                  <td>
                    <span style={{ color: t.overdue ? "#b06464" : "inherit" }}>{dueLabel(t.due_at, t.overdue, now)}</span>
                  </td>
                  <td>{t.owner?.name ?? "Chưa phân công"}</td>
                  <td>
                    <Pill tone={TASK_STATUS[t.status].tone}>{TASK_STATUS[t.status].label}</Pill>
                  </td>
                  <td>
                    <button type="button" onClick={() => setOpenId(t.id)}>
                      Xử lý
                    </button>
                  </td>
                </tr>
              ))}
            </DataTable>
            <ul className="cardlist">
              {rows.map((t) => (
                <li key={t.id} className="card">
                  <div className="row">
                    <b>{t.contact?.name ?? t.title}</b>
                    <Pill tone={TASK_STATUS[t.status].tone}>{TASK_STATUS[t.status].label}</Pill>
                  </div>
                  <p>
                    {TASK_TYPE[t.type]} · <span style={{ color: t.overdue ? "#b06464" : "inherit" }}>{dueLabel(t.due_at, t.overdue, now)}</span>
                  </p>
                  <p>{t.owner?.name ?? "Chưa phân công"}</p>
                  <button type="button" style={{ marginTop: 8 }} onClick={() => setOpenId(t.id)}>
                    Xử lý
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      {open && <ProcessTaskModal key={open.id} task={open} members={members} onClose={() => setOpenId(null)} />}
      {creating && <CreateTaskModal members={members} onClose={() => setCreating(false)} />}
      <p className="small" style={{ marginTop: 12 }}>
        Quá hạn tính theo đồng hồ máy chủ. Muốn xem cuộc gọi gốc, mở yêu cầu rồi chọn <Link className="link" href="/cuoc-goi">cuộc gọi liên quan</Link>.
      </p>
    </>
  );
}
