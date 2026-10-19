"use client";

import { useState } from "react";

import { CreateTaskModal } from "@/components/tasks/TaskForms";
import type { Member } from "@/lib/api";

export function HandoffActions({
  members,
  callId,
  contactId,
  contactName,
}: {
  members: Member[];
  callId: string | null;
  contactId: string | null;
  contactName: string | null;
}) {
  const [receiver, setReceiver] = useState(members[0]?.user_id ?? "");
  const [callback, setCallback] = useState(false);
  return (
    <>
      <div className="field">
        <label htmlFor="h-receiver">Chọn người nhận</label>
        <select id="h-receiver" value={receiver} onChange={(e) => setReceiver(e.target.value)}>
          {members.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.name}
            </option>
          ))}
        </select>
        <div className="small">Trạng thái sẵn sàng của máy nhánh có khi kết nối tổng đài.</div>
      </div>
      <div className="actions" style={{ margin: "18px 0" }}>
        <button type="button" className="primary" disabled aria-describedby="h-why">
          Gửi yêu cầu bàn giao
        </button>
        <button type="button" onClick={() => setCallback(true)}>
          Tạo việc gọi lại
        </button>
      </div>
      <div className="notice" id="h-why">
        Chuyển máy trực tiếp cần tổng đài thật (ADR 0004). Bàn giao chỉ được tính là thành công khi tổng đài xác nhận
        nhân viên đã nhận máy; trong lúc chưa có, hãy tạo việc gọi lại để khách không bị bỏ sót.
      </div>
      {callback && (
        <CreateTaskModal
          members={members}
          onClose={() => setCallback(false)}
          defaults={{
            title: "Gọi lại sau yêu cầu gặp nhân viên",
            type: "callback",
            callId: callId ?? undefined,
            contactId: contactId ?? undefined,
            contactName: contactName ?? undefined,
          }}
        />
      )}
    </>
  );
}
