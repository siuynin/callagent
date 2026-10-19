import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Notice, PageHead, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";

import { AgentsView } from "./AgentsView";

export const metadata: Metadata = { title: "Voice Agents" };

async function AgentsData() {
  await connection();
  const [agents, me] = await Promise.all([api.agents().catch(() => null), api.me().catch(() => null)]);
  if (!agents) {
    return (
      <Notice tone="bad" role="alert">
        Không tải được danh sách agent.
      </Notice>
    );
  }
  const canCreate = !!me && ["owner", "admin", "manager"].includes(me.role);
  return <AgentsView agents={agents.items} canCreate={canCreate} />;
}

export default function AgentsPage() {
  return (
    <>
      <PageHead title="Voice Agents" sub="Thiết lập đội ngũ trợ lý AI theo mục tiêu và nghiệp vụ." />
      <Suspense fallback={<Skeleton label="Đang tải agent" />}>
        <AgentsData />
      </Suspense>
    </>
  );
}
