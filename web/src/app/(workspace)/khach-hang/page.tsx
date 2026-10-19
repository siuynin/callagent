import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { api, ApiError, type Contact } from "@/lib/api";

export const metadata: Metadata = { title: "Khách hàng" };

const PHONE_STATUS: Record<Contact["phone_status"], { label: string; cls: string }> = {
  valid: { label: "Hợp lệ", cls: "badge" },
  uncertain: { label: "Cần kiểm tra", cls: "badge warn" },
  invalid: { label: "Sai số", cls: "badge bad" },
};

function PhoneBadge({ status }: { status: Contact["phone_status"] }) {
  const s = PHONE_STATUS[status];
  return <span className={s.cls}>{s.label}</span>;
}

async function ContactList() {
  await connection();
  let items: Contact[] = [];
  let failure: string | null = null;
  try {
    items = (await api.contacts()).items;
  } catch (e) {
    failure =
      e instanceof ApiError && e.status === 401
        ? "Chưa đăng nhập. Ở môi trường dev, đặt DEV_AUTH_TOKEN trong web/.env.local (xem README)."
        : "Không tải được danh sách khách hàng.";
  }
  if (failure) {
    return (
      <div className="banner bad" role="alert">
        {failure}
      </div>
    );
  }
  if (!items.length) {
    return <p className="muted">Chưa có khách hàng nào.</p>;
  }
  return (
    <>
      <div className="card tablewrap responsive">
        <table>
          <thead>
            <tr>
              <th>Khách hàng</th>
              <th>Số điện thoại</th>
              <th>Kiểm tra số</th>
              <th>Nhu cầu</th>
            </tr>
          </thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.normalized_phone ?? c.phone_raw}</td>
                <td>
                  <PhoneBadge status={c.phone_status} />
                </td>
                <td>{c.need ?? "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="cardlist" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {items.map((c) => (
          <li key={c.id} className="card">
            <b>{c.name}</b> <PhoneBadge status={c.phone_status} />
            <div className="muted">{c.normalized_phone ?? c.phone_raw}</div>
            {c.need && <div>{c.need}</div>}
          </li>
        ))}
      </ul>
    </>
  );
}

export default function ContactsPage() {
  return (
    <>
      <header className="pagehead">
        <h1>Khách hàng</h1>
        <p className="muted">Số điện thoại được chuẩn hóa về +84; số mất chữ số đầu được đánh dấu cần kiểm tra, không tự đoán.</p>
      </header>
      <Suspense fallback={<div className="skeleton" aria-label="Đang tải khách hàng" />}>
        <ContactList />
      </Suspense>
    </>
  );
}
