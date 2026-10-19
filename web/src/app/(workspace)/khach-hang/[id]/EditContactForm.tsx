"use client";

import { useActionState, useEffect, useState } from "react";

import { useToast } from "@/components/ui/Toast";
import type { Contact } from "@/lib/api";
import { submitTo } from "@/lib/forms";

import { type FormState, updateContactAction } from "../actions";

const INITIAL: FormState = { ok: false };

export function EditContactForm({ contact }: { contact: Contact }) {
  const toast = useToast();
  const [state, action, pending] = useActionState(updateContactAction, INITIAL);
  // controlled: keep edits visible when the server rejects them (e.g. version conflict)
  const [name, setName] = useState(contact.name);
  const [need, setNeed] = useState(contact.need ?? "");

  useEffect(() => {
    if (state.ok) toast("Đã lưu hồ sơ khách hàng");
  }, [state, toast]);

  return (
    <form onSubmit={submitTo(action)} noValidate>
      <input type="hidden" name="id" value={contact.id} />
      <input type="hidden" name="version" value={contact.version} />
      <div className="field">
        <label htmlFor="e-name">Tên khách hàng</label>
        <input id="e-name" name="name" value={name} onChange={(e) => setName(e.target.value)} aria-invalid={!!state.fieldErrors?.name} />
        {state.fieldErrors?.name && <div className="fielderror">{state.fieldErrors.name}</div>}
      </div>
      <div className="field">
        <label htmlFor="e-need">Nhu cầu</label>
        <input id="e-need" name="need" value={need} onChange={(e) => setNeed(e.target.value)} />
      </div>
      <div className="field">
        <label>Nhân viên phụ trách</label>
        <select disabled aria-describedby="owner-hint">
          <option>Chưa phân công</option>
        </select>
        <div className="small" id="owner-hint">
          Phân công nhân viên có từ M1 (cần danh sách thành viên).
        </div>
      </div>
      {state.message && (
        <div className="fielderror" role="alert" style={{ marginBottom: 12 }}>
          {state.message}
        </div>
      )}
      <div className="actions">
        <button type="submit" className="primary" disabled={pending}>
          {pending ? "Đang lưu…" : "Lưu thay đổi"}
        </button>
        <span className="small">Phiên bản {contact.version}</span>
      </div>
    </form>
  );
}
