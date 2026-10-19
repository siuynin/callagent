"use client";

import Link from "next/link";
import { useActionState, useEffect, useMemo, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { DataTable, Empty, Pill } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toast";
import type { Contact } from "@/lib/api";
import { PHONE_STATUS } from "@/lib/contacts";
import { fold } from "@/lib/text";

import { createContactAction, type FormState } from "./actions";

export function ContactsView({ contacts }: { contacts: Contact[] }) {
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const list = useMemo(() => {
    const q = fold(query.trim());
    const digits = query.replace(/\D/g, "");
    if (!q) return contacts;
    return contacts.filter(
      (c) => fold(c.name).includes(q) || (digits && (c.phone_raw + (c.normalized_phone ?? "")).replace(/\D/g, "").includes(digits)),
    );
  }, [contacts, query]);

  return (
    <>
      <div className="toolbar">
        <input
          placeholder="⌕  Tìm tên hoặc số điện thoại…"
          aria-label="Tìm khách hàng"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="small">{list.length} khách hàng</span>
        <div className="right">
          <button type="button" className="primary" onClick={() => setAdding(true)}>
            + Thêm khách hàng
          </button>
        </div>
      </div>
      <div className="card">
        {list.length === 0 ? (
          <div className="pad">
            <Empty>{contacts.length ? "Không có khách hàng khớp từ khóa." : "Chưa có khách hàng nào."}</Empty>
          </div>
        ) : (
          <>
            <DataTable heads={["Khách hàng", "Nhu cầu", "Số điện thoại", "Ngày tạo", ""]} responsive>
              {list.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link className="link" href={`/khach-hang/${c.id}`}>
                      {c.name}
                    </Link>
                    <small>{c.normalized_phone ?? c.phone_raw}</small>
                  </td>
                  <td>{c.need ?? "–"}</td>
                  <td>
                    <Pill tone={PHONE_STATUS[c.phone_status].tone}>{PHONE_STATUS[c.phone_status].label}</Pill>
                  </td>
                  <td>{new Date(c.created_at).toLocaleDateString("vi-VN")}</td>
                  <td>
                    <Link className="btn" href={`/khach-hang/${c.id}`}>
                      Mở hồ sơ
                    </Link>
                  </td>
                </tr>
              ))}
            </DataTable>
            <ul className="cardlist">
              {list.map((c) => (
                <li key={c.id} className="card">
                  <div className="row">
                    <Link className="link" href={`/khach-hang/${c.id}`}>
                      {c.name}
                    </Link>
                    <Pill tone={PHONE_STATUS[c.phone_status].tone}>{PHONE_STATUS[c.phone_status].label}</Pill>
                  </div>
                  <p>{c.normalized_phone ?? c.phone_raw}</p>
                  {c.need && <p>{c.need}</p>}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      {adding && <AddContactModal onClose={() => setAdding(false)} />}
    </>
  );
}

const INITIAL: FormState = { ok: false };

function AddContactModal({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const [key] = useState(() => crypto.randomUUID());
  const [state, action, pending] = useActionState(createContactAction, INITIAL);

  useEffect(() => {
    if (state.ok) {
      toast(state.phoneWarning ? `Đã thêm khách hàng. ${state.phoneWarning}` : "Đã thêm khách hàng");
      onClose();
    }
  }, [state, toast, onClose]);

  return (
    <Modal
      title="Thêm khách hàng"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose}>
            Hủy
          </button>
          <button type="submit" form="addcontact" className="primary" disabled={pending}>
            {pending ? "Đang lưu…" : "Lưu khách hàng"}
          </button>
        </>
      }
    >
      <form id="addcontact" action={action} noValidate>
        <input type="hidden" name="idempotency_key" value={key} />
        <div className="field">
          <label htmlFor="c-name">Tên khách hàng *</label>
          <input id="c-name" name="name" autoComplete="off" aria-invalid={!!state.fieldErrors?.name} />
          {state.fieldErrors?.name && <div className="fielderror">{state.fieldErrors.name}</div>}
        </div>
        <div className="field">
          <label htmlFor="c-phone">Số điện thoại *</label>
          <input id="c-phone" name="phone" inputMode="tel" autoComplete="off" aria-invalid={!!state.fieldErrors?.phone} />
          {state.fieldErrors?.phone && <div className="fielderror">{state.fieldErrors.phone}</div>}
          <div className="small">Tự chuẩn hóa về +84. Số thiếu chữ số đầu được đánh dấu cần kiểm tra, không tự đoán.</div>
        </div>
        <div className="field">
          <label htmlFor="c-need">Nhu cầu</label>
          <input id="c-need" name="need" placeholder="Ví dụ: lái thử SUV" />
        </div>
        {state.message && <div className="fielderror" role="alert">{state.message}</div>}
      </form>
    </Modal>
  );
}
