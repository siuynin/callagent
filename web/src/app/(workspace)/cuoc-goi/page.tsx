import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Notice, PageHead, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";

import { CallsView } from "./CallsView";

export const metadata: Metadata = { title: "Cuộc gọi" };

async function CallsData() {
  await connection();
  const calls = await api.calls(100).catch(() => null);
  if (!calls) {
    return (
      <Notice tone="bad" role="alert">
        Không tải được cuộc gọi.
      </Notice>
    );
  }
  return <CallsView calls={calls.items} />;
}

export default function CallsPage() {
  return (
    <>
      <PageHead title="Cuộc gọi" sub="Tra cứu hội thoại và theo dõi kết quả xử lý." />
      <Suspense fallback={<Skeleton label="Đang tải cuộc gọi" />}>
        <CallsData />
      </Suspense>
    </>
  );
}
