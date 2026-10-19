"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";

import { createTaskAction, type TaskFormState, updateTaskAction } from "@/app/actions/tasks";
import { Modal } from "@/components/ui/Modal";
import { Pill } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toast";
import type { Member, Task, TaskType } from "@/lib/api";
import { TASK_STATUS, TASK_TYPE } from "@/lib/labels";
import { submitTo } from "@/lib/forms";

const INITIAL: TaskFormState = { ok: false };

function FieldError({ msg }: { msg?: string }) {
  return msg ? <div className="fielderror">{msg}</div> : null;
}

/** Template "Xử lý yêu cầu" modal; rules are enforced by the API and surfaced per field. */
export function ProcessTaskModal({ task: live, members, onClose }: { task: Task; members: Member[]; onClose: () => void }) {
  const toast = useToast();
  // snapshot at open: our own save refreshes the list underneath; a concurrent edit by someone else
  // must still surface as a version conflict instead of being overwritten silently
  const [task] = useState(live);
  const [state, action, pending] = useActionState(updateTaskAction, INITIAL);
  const closed = task.status === "resolved" || task.status === "cancelled";
  // controlled + submitTo(): keep the user's choices when the server rejects them
  const [owner, setOwner] = useState(task.owner?.id ?? "");
  const [status, setStatus] = useState<string>(task.status);
  const [note, setNote] = useState(task.resolution_note ?? "");

  useEffect(() => {
    if (state.ok) {
      toast("Đã cập nhật công việc");
      onClose();
    }
  }, [state, toast, onClose]);

  return (
    <Modal
      title={`Xử lý yêu cầu · ${TASK_TYPE[task.type]}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose}>
            Đóng
          </button>
          {task.type === "human_request" && !closed && (
            <Link className="btn" href={`/ban-giao?task=${task.id}`} onClick={onClose}>
              Bàn giao nhân viên
            </Link>
          )}
          {!closed && (
            <button type="submit" form="processtask" className="primary" disabled={pending}>
              {pending ? "Đang lưu…" : "Lưu cập nhật"}
            </button>
          )}
        </>
      }
    >
      <p style={{ marginBottom: 16 }}>
        <b style={{ color: "#354050" }}>{task.contact?.name ?? "Không gắn khách"}</b> · {task.title}
      </p>
      {closed ? (
        <div className="notice">
          Công việc đã {TASK_STATUS[task.status].label.toLowerCase()}. Kết quả: {task.resolution_note ?? "–"}
        </div>
      ) : (
        <form id="processtask" onSubmit={submitTo(action)} noValidate>
          <input type="hidden" name="id" value={task.id} />
          <input type="hidden" name="version" value={task.version} />
          <input type="hidden" name="orig_owner_id" value={task.owner?.id ?? ""} />
          <input type="hidden" name="orig_status" value={task.status} />
          <input type="hidden" name="orig_note" value={task.resolution_note ?? ""} />
          <div className="field">
            <label htmlFor="t-owner">Người phụ trách</label>
            <select
              id="t-owner"
              name="owner_id"
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
              aria-invalid={!!state.fieldErrors?.owner_id}
            >
              <option value="">Chưa phân công</option>
              {members.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.name}
                </option>
              ))}
            </select>
            <FieldError msg={state.fieldErrors?.owner_id} />
          </div>
          <div className="field">
            <label htmlFor="t-status">Trạng thái</label>
            <select id="t-status" name="status" value={status} onChange={(e) => setStatus(e.target.value)}>
              {(["new", "in_progress", "resolved", "cancelled"] as const).map((s) => (
                <option key={s} value={s}>
                  {TASK_STATUS[s].label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="t-note">Ghi chú / kết quả xử lý</label>
            <textarea
              id="t-note"
              name="resolution_note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Bắt buộc khi chuyển sang Hoàn thành"
              aria-invalid={!!state.fieldErrors?.resolution_note}
            />
            <FieldError msg={state.fieldErrors?.resolution_note} />
          </div>
          {state.message && (
            <div className="fielderror" role="alert">
              {state.message}
            </div>
          )}
          {task.call_id && (
            <p style={{ marginTop: 12 }}>
              <Link className="link" href={`/cuoc-goi/${task.call_id}`} onClick={onClose}>
                Mở cuộc gọi liên quan →
              </Link>
            </p>
          )}
        </form>
      )}
    </Modal>
  );
}

export function CreateTaskModal({
  members,
  onClose,
  defaults,
}: {
  members: Member[];
  onClose: () => void;
  defaults?: { title?: string; type?: TaskType; contactId?: string; callId?: string; contactName?: string };
}) {
  const toast = useToast();
  const [key] = useState(() => crypto.randomUUID());
  const [state, action, pending] = useActionState(createTaskAction, INITIAL);
  const [form, setForm] = useState({
    title: defaults?.title ?? "",
    type: defaults?.type ?? "follow_up",
    priority: "normal",
    due_at: "",
    owner_id: "",
  });
  const bind = (k: keyof typeof form) => ({
    name: k,
    value: form[k],
    onChange: (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value })),
  });

  useEffect(() => {
    if (state.ok) {
      toast("Đã tạo công việc");
      onClose();
    }
  }, [state, toast, onClose]);

  return (
    <Modal
      title="Tạo công việc"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose}>
            Hủy
          </button>
          <button type="submit" form="createtask" className="primary" disabled={pending}>
            {pending ? "Đang lưu…" : "Tạo công việc"}
          </button>
        </>
      }
    >
      <form id="createtask" onSubmit={submitTo(action)} noValidate>
        <input type="hidden" name="idempotency_key" value={key} />
        {defaults?.contactId && <input type="hidden" name="contact_id" value={defaults.contactId} />}
        {defaults?.callId && <input type="hidden" name="call_id" value={defaults.callId} />}
        {defaults?.contactName && (
          <p style={{ marginBottom: 14 }}>
            Khách: <Pill>{defaults.contactName}</Pill>
          </p>
        )}
        <div className="field">
          <label htmlFor="n-title">Nội dung *</label>
          <input id="n-title" {...bind("title")} aria-invalid={!!state.fieldErrors?.title} />
          <FieldError msg={state.fieldErrors?.title} />
        </div>
        <div className="field">
          <label htmlFor="n-type">Loại</label>
          <select id="n-type" {...bind("type")}>
            {Object.entries(TASK_TYPE).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="n-priority">Ưu tiên</label>
          <select id="n-priority" {...bind("priority")}>
            <option value="normal">Thường</option>
            <option value="high">Cao</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="n-due">Hạn xử lý (giờ Việt Nam)</label>
          <input id="n-due" type="datetime-local" {...bind("due_at")} />
        </div>
        <div className="field">
          <label htmlFor="n-owner">Người phụ trách</label>
          <select id="n-owner" {...bind("owner_id")}>
            <option value="">Chưa phân công</option>
            {members.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
        {state.message && (
          <div className="fielderror" role="alert">
            {state.message}
          </div>
        )}
      </form>
    </Modal>
  );
}
