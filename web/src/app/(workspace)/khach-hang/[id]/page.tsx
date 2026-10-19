import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { Card, Notice, PageHead, Pill, Skeleton } from "@/components/ui/primitives";
import { api, ApiError, type Contact } from "@/lib/api";
import { PHONE_STATUS } from "@/lib/contacts";

import { EditContactForm } from "./EditContactForm";

export const metadata: Metadata = { title: "Hồ sơ khách hàng" };

async function Profile({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await connection();
  let contact: Contact;
  try {
    contact = (await api.contact(id)).data;
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422 || e.status === 400)) notFound();
    return (
      <Notice tone="bad" role="alert">
        Không tải được hồ sơ khách hàng.
      </Notice>
    );
  }
  const phone = contact.normalized_phone ?? contact.phone_raw;
  const status = PHONE_STATUS[contact.phone_status];
  return (
    <>
      <PageHead
        title={contact.name}
        sub={`Hồ sơ khách hàng · ${phone}`}
        actions={
          <Link className="btn" href="/khach-hang">
            ← Khách hàng
          </Link>
        }
      />
      <div className="grid cols">
        <Card title="Lịch sử tương tác">
          <div className="pad timeline" style={{ margin: 24 }}>
            <div>
              <h3>{new Date(contact.created_at).toLocaleString("vi-VN")} — Tạo hồ sơ</h3>
              <p>
                Số điện thoại: {phone} · <Pill tone={status.tone}>{status.label}</Pill>
              </p>
            </div>
            <div>
              <h3>Cuộc gọi, lịch hẹn, bàn giao</h3>
              <p>Sẽ hiển thị tại đây khi lễ tân AI và hộp việc chạy thật (M1).</p>
            </div>
          </div>
        </Card>
        <Card title="Thông tin & chăm sóc">
          <div className="pad">
            <EditContactForm contact={contact} />
          </div>
        </Card>
      </div>
    </>
  );
}

// params are request data: read them inside Suspense so the shell can be prerendered
export default function ContactPage({ params }: PageProps<"/khach-hang/[id]">) {
  return (
    <Suspense fallback={<Skeleton label="Đang tải hồ sơ" />}>
      <Profile params={params} />
    </Suspense>
  );
}
