import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Notice, PageHead, Skeleton, Stats } from "@/components/ui/primitives";
import { api } from "@/lib/api";

import { InboxView } from "./InboxView";

export const metadata: Metadata = { title: "Hộp việc cần xử lý" };

async function InboxData() {
  await connection();
  const [tasks, summary, members] = await Promise.all([
    api.tasks().catch(() => null),
    api.taskSummary().catch(() => null),
    api.members().catch(() => ({ items: [] })),
  ]);
  if (!tasks || !summary) {
    return (
      <Notice tone="bad" role="alert">
        Không tải được hộp việc.
      </Notice>
    );
  }
  return (
    <>
      <Stats
        items={[
          { label: "Chưa phân công", value: summary.unassigned, foot: "Cần người tiếp nhận" },
          { label: "Quá hạn", value: summary.overdue, foot: "Ưu tiên xử lý" },
          { label: "Đang xử lý", value: summary.in_progress, foot: "Đã có người phụ trách" },
          { label: "Hoàn thành", value: summary.resolved, foot: "Tổng đã đóng" },
        ]}
      />
      <InboxView tasks={tasks.items} members={members.items} now={new Date().toISOString()} />
    </>
  );
}

export default function InboxPage() {
  return (
    <>
      <PageHead title="Hộp việc cần xử lý" sub="Mỗi yêu cầu có người phụ trách, thời hạn và kết quả rõ ràng." />
      <Suspense fallback={<Skeleton label="Đang tải hộp việc" />}>
        <InboxData />
      </Suspense>
    </>
  );
}
