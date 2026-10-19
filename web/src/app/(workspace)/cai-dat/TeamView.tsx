"use client";

import { useActionState, useEffect, useState } from "react";

import { changeRoleAction, inviteMemberAction, type MemberState, removeMemberAction } from "@/app/actions/members";
import { Modal } from "@/components/ui/Modal";
import { DataTable, Notice, Pill } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toast";
import type { AdminMember, Me } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/labels";
import { submitTo } from "@/lib/forms";

const ROLE_SCOPE: Record<Me["role"], string> = {
  owner: "Toàn bộ workspace, kể cả quyền chủ sở hữu",
  admin: "Toàn bộ workspace, xuất bản agent, thành viên",
  manager: "Agent (bản nháp), công việc, báo cáo",
  staff: "Khách hàng và công việc được phân công",
  auditor: "Chỉ đọc",
};
const INITIAL: MemberState = { ok: false };

function useResult(state: MemberState) {
  const toast = useToast();
  useEffect(() => {
    if (state.ok && state.message) toast(state.message);
  }, [state, toast]);
}

function RoleCell({ m, myRole, isSelf }: { m: AdminMember; myRole: Me["role"]; isSelf: boolean }) {
  const [state, action, pending] = useActionState(changeRoleAction, INITIAL);
  const [role, setRole] = useState(m.role);
  useResult(state);
  const roles = (Object.keys(ROLE_LABEL) as Me["role"][]).filter((r) => r !== "owner" || myRole === "owner");
  if (isSelf || (m.role === "owner" && myRole !== "owner")) return <span>{ROLE_LABEL[m.role]}</span>;
  return (
    <form onSubmit={submitTo(action)} style={{ display: "flex", gap: 6, alignItems: "center" }}>
      <input type="hidden" name="user_id" value={m.user_id} />
      <select name="role" aria-label={`Vai trò của ${m.name}`} value={role} onChange={(e) => setRole(e.target.value as Me["role"])}>
        {roles.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABEL[r]}
          </option>
        ))}
      </select>
      {role !== m.role && (
        <button type="submit" disabled={pending}>
          Lưu
        </button>
      )}
      {!state.ok && state.message && <span className="fielderror" role="alert">{state.message}</span>}
    </form>
  );
}

function RemoveButton({ m }: { m: AdminMember }) {
  const [state, action, pending] = useActionState(removeMemberAction, INITIAL);
  const [confirming, setConfirming] = useState(false);
  useResult(state);
  return (
    <>
      <button type="button" className="flat" style={{ color: "#b06464" }} onClick={() => setConfirming(true)}>
        Gỡ
      </button>
      {confirming && !state.ok && (
        <Modal
          title="Gỡ thành viên"
          onClose={() => setConfirming(false)}
          footer={
            <>
              <button type="button" onClick={() => setConfirming(false)}>
                Hủy
              </button>
              <button type="submit" form={`rm-${m.user_id}`} className="primary" disabled={pending}>
                Gỡ khỏi workspace
              </button>
            </>
          }
        >
          <form id={`rm-${m.user_id}`} onSubmit={submitTo(action)}>
            <input type="hidden" name="user_id" value={m.user_id} />
            <p>
              Gỡ <b>{m.name}</b> ({m.email}) khỏi workspace? Người này mất quyền truy cập ngay; các việc đang mở của họ trở về
              &quot;chưa phân công&quot;.
            </p>
            {state.message && <div className="fielderror" role="alert">{state.message}</div>}
          </form>
        </Modal>
      )}
    </>
  );
}

function InviteModal({ myRole, onClose }: { myRole: Me["role"]; onClose: () => void }) {
  const [state, action, pending] = useActionState(inviteMemberAction, INITIAL);
  const [v, setV] = useState({ email: "", display_name: "", role: "staff" });
  const toast = useToast();
  useEffect(() => {
    if (state.ok) {
      toast(state.message ?? "Đã mời");
      onClose();
    }
  }, [state, toast, onClose]);
  const bind = (k: keyof typeof v) => ({ name: k, value: v[k], onChange: (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value })) });
  return (
    <Modal
      title="Mời thành viên"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose}>
            Hủy
          </button>
          <button type="submit" form="invite" className="primary" disabled={pending}>
            {pending ? "Đang mời…" : "Mời"}
          </button>
        </>
      }
    >
      <form id="invite" onSubmit={submitTo(action)} noValidate>
        <div className="field">
          <label htmlFor="i-email">Email đăng nhập *</label>
          <input id="i-email" type="email" autoComplete="off" {...bind("email")} />
          {state.fieldErrors?.email && <div className="fielderror">{state.fieldErrors.email}</div>}
          <div className="small">Phải trùng email tài khoản công ty mà người này dùng để đăng nhập.</div>
        </div>
        <div className="field">
          <label htmlFor="i-name">Tên hiển thị *</label>
          <input id="i-name" {...bind("display_name")} />
          {state.fieldErrors?.display_name && <div className="fielderror">{state.fieldErrors.display_name}</div>}
        </div>
        <div className="field">
          <label htmlFor="i-role">Vai trò</label>
          <select id="i-role" {...bind("role")}>
            {(Object.keys(ROLE_LABEL) as Me["role"][])
              .filter((r) => r !== "owner" || myRole === "owner")
              .map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]} · {ROLE_SCOPE[r]}
                </option>
              ))}
          </select>
        </div>
        {state.message && !state.ok && <div className="fielderror" role="alert">{state.message}</div>}
      </form>
    </Modal>
  );
}

export function TeamView({ members, me, oidc }: { members: AdminMember[]; me: Me; oidc: boolean }) {
  const [inviting, setInviting] = useState(false);
  return (
    <>
      {!oidc && <Notice tone="warn">Đăng nhập OIDC chưa bật (môi trường dev dùng token dev). Lời mời vẫn được lưu và có hiệu lực khi bật OIDC.</Notice>}
      <section className="card">
        <div className="cardhead">
          <h2>Thành viên & phân quyền</h2>
          <button type="button" className="primary" onClick={() => setInviting(true)}>
            + Mời thành viên
          </button>
        </div>
        <DataTable heads={["Thành viên", "Vai trò", "Phạm vi", "Trạng thái", "Đăng nhập gần nhất", ""]}>
          {members.map((m) => {
            const isSelf = m.user_id === me.user_id;
            return (
              <tr key={m.user_id}>
                <td>
                  <span className="avatar">{m.name.slice(0, 1).toUpperCase()}</span>
                  {m.name}
                  {isSelf && <span className="small"> (bạn)</span>}
                  <small>{m.email}</small>
                </td>
                <td>
                  <RoleCell m={m} myRole={me.role} isSelf={isSelf} />
                </td>
                <td>{ROLE_SCOPE[m.role]}</td>
                <td>{m.status === "active" ? <Pill tone="green">Đã tham gia</Pill> : <Pill tone="amber">Đã mời</Pill>}</td>
                <td>{m.last_login_at ? new Date(m.last_login_at).toLocaleString("vi-VN") : "–"}</td>
                <td>{!isSelf && !(m.role === "owner" && me.role !== "owner") && <RemoveButton m={m} />}</td>
              </tr>
            );
          })}
        </DataTable>
      </section>
      {inviting && <InviteModal myRole={me.role} onClose={() => setInviting(false)} />}
    </>
  );
}
