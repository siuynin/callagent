import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { Notice, PageHead, Skeleton } from "@/components/ui/primitives";
import { type Agent, api, ApiError } from "@/lib/api";

import { AgentEditor } from "./AgentEditor";

export const metadata: Metadata = { title: "Cấu hình agent" };

async function Editor({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await connection();
  let agent: Agent;
  try {
    agent = (await api.agent(id)).data;
  } catch (e) {
    if (e instanceof ApiError && [400, 404, 422].includes(e.status)) notFound();
    return (
      <Notice tone="bad" role="alert">
        Không tải được agent.
      </Notice>
    );
  }
  const me = await api.me().catch(() => null);
  const role = me?.role ?? "auditor";
  const sub = [
    agent.active_version ? `Đang hoạt động v${agent.active_version.number}` : "Chưa xuất bản",
    agent.draft ? `Bản nháp v${agent.draft.number}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <>
      <PageHead
        title={agent.name}
        sub={sub}
        actions={
          <Link className="btn" href="/agents">
            ← Voice Agents
          </Link>
        }
      />
      {/* keyed on agent.version: a save/publish elsewhere re-initialises the form from the server copy */}
      <AgentEditor
        key={agent.version}
        agent={agent}
        canEdit={["owner", "admin", "manager"].includes(role)}
        canPublish={["owner", "admin"].includes(role)}
      />
    </>
  );
}

export default function AgentPage({ params }: PageProps<"/agents/[id]">) {
  return (
    <Suspense fallback={<Skeleton label="Đang tải agent" />}>
      <Editor params={params} />
    </Suspense>
  );
}
