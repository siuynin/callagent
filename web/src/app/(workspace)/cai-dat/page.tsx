import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Card, DataTable, Notice, PageHead, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/labels";
import { oidcEnabled } from "@/lib/session";

import { TeamView } from "./TeamView";

export const metadata: Metadata = { title: "Cài đặt" };

async function Team() {
  await connection();
  const me = await api.me().catch(() => null);
  if (!me) {
    return (
      <Notice tone="bad" role="alert">
        Không tải được thông tin tài khoản.
      </Notice>
    );
  }
  if (me.role === "owner" || me.role === "admin") {
    const members = await api.adminMembers().catch(() => null);
    if (!members) return <Notice tone="bad">Không tải được danh sách thành viên.</Notice>;
    return <TeamView members={members.items} me={me} oidc={oidcEnabled()} />;
  }
  // everyone else sees the directory read-only (names and roles, no emails)
  const directory = await api.members().catch(() => ({ items: [] }));
  return (
    <Card title="Thành viên">
      <DataTable heads={["Thành viên", "Vai trò"]}>
        {directory.items.map((m) => (
          <tr key={m.user_id}>
            <td>{m.name}</td>
            <td>{ROLE_LABEL[m.role]}</td>
          </tr>
        ))}
      </DataTable>
      <div className="foot">
        <span>Chỉ quản trị viên mới mời, đổi vai trò hoặc gỡ thành viên.</span>
      </div>
    </Card>
  );
}

export default function SettingsPage() {
  return (
    <>
      <PageHead title="Cài đặt workspace" sub="Quản lý đội ngũ, quyền truy cập và chính sách dữ liệu." />
      <div className="tabs">
        <button type="button" className="active">
          Đội ngũ
        </button>
        <button type="button" disabled title="Có ở các bước sau">
          Dữ liệu & bảo mật
        </button>
        <button type="button" disabled title="Có ở các bước sau">
          Nhật ký
        </button>
      </div>
      <Suspense fallback={<Skeleton label="Đang tải thành viên" />}>
        <Team />
      </Suspense>
    </>
  );
}
