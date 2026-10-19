import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Notice, PageHead, Skeleton } from "@/components/ui/primitives";
import { api, ApiError, type Contact } from "@/lib/api";

import { ContactsView } from "./ContactsView";

export const metadata: Metadata = { title: "Khách hàng" };

async function ContactsData() {
  await connection();
  let contacts: Contact[] = [];
  let failure: string | null = null;
  try {
    contacts = (await api.contacts()).items;
  } catch (e) {
    failure =
      e instanceof ApiError && e.status === 401
        ? "Chưa đăng nhập. Ở môi trường dev, đặt DEV_AUTH_TOKEN trong web/.env.local (xem README)."
        : "Không tải được danh sách khách hàng.";
  }
  if (failure) {
    return (
      <Notice tone="bad" role="alert">
        {failure}
      </Notice>
    );
  }
  return <ContactsView contacts={contacts} />;
}

export default function ContactsPage() {
  return (
    <>
      <PageHead title="Khách hàng" sub="Tập trung thông tin liên hệ, nhu cầu và lịch sử chăm sóc." />
      <Suspense fallback={<Skeleton label="Đang tải khách hàng" />}>
        <ContactsData />
      </Suspense>
    </>
  );
}
