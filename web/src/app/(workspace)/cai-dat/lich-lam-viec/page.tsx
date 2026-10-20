import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Notice, PageHead, Skeleton } from "@/components/ui/primitives";
import { api, ApiError } from "@/lib/api";

import { SettingsTabs } from "../SettingsTabs";
import { CalendarView } from "./CalendarView";

export const metadata: Metadata = { title: "Lịch làm việc" };

async function Calendar() {
  await connection();
  const me = await api.me().catch(() => null);
  const data = await Promise.all([api.calendars(), api.inboundRoutes(), api.members()]).catch((e: unknown) =>
    e instanceof ApiError && e.status === 403 ? ("forbidden" as const) : null,
  );
  if (data === "forbidden") {
    return <Notice tone="warn">Chỉ quản lý và quản trị viên xem được lịch làm việc và định tuyến.</Notice>;
  }
  const [calendars, routes, members] = data ?? [];
  const calendar = calendars?.items[0];
  const route = routes?.items.find((r) => r.number === "*") ?? routes?.items[0];
  if (!calendar || !route || !members) {
    return (
      <Notice tone="bad" role="alert">
        Không tải được lịch làm việc.
      </Notice>
    );
  }
  return (
    <CalendarView
      calendar={calendar}
      route={route}
      owners={members.items.filter((m) => m.role !== "auditor")}
      canEdit={me?.role === "owner" || me?.role === "admin"}
    />
  );
}

export default function WorkingHoursPage() {
  return (
    <>
      <PageHead
        title="Cài đặt workspace"
        sub="Giờ làm việc và ngày nghỉ quyết định ai trả lời cuộc gọi đến và hạn xử lý việc phát sinh ngoài giờ."
      />
      <SettingsTabs active="/cai-dat/lich-lam-viec" />
      <Suspense fallback={<Skeleton label="Đang tải lịch làm việc" />}>
        <Calendar />
      </Suspense>
    </>
  );
}
