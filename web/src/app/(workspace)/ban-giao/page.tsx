import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";

import { Card, Empty, Notice, PageHead, Pill, Skeleton } from "@/components/ui/primitives";
import { api, type CallDetail, type Task } from "@/lib/api";
import { PRIORITY, TASK_STATUS } from "@/lib/labels";

import { HandoffActions } from "./HandoffActions";

export const metadata: Metadata = { title: "Bàn giao nhân viên" };

function handoffQueued(result: Record<string, unknown> | null): boolean {
  const data = (result?.data as Record<string, unknown> | undefined) ?? {};
  return result?.handoff_status === "queued" || data.handoff_status === "queued";
}

function Queue({ tasks, selected }: { tasks: Task[]; selected?: string }) {
  if (!tasks.length) {
    return (
      <div className="pad">
        <Empty>Không có khách nào đang chờ gặp nhân viên.</Empty>
      </div>
    );
  }
  return (
    <div className="pad" style={{ display: "grid", gap: 8 }}>
      {tasks.map((t) => (
        <Link
          key={t.id}
          href={`/ban-giao?task=${t.id}`}
          className="quick"
          aria-current={t.id === selected ? "true" : undefined}
          style={t.id === selected ? { borderColor: "#7fb59f" } : undefined}
        >
          <div>
            <b>{t.contact?.name ?? "Số lạ"}</b>
            <p>{t.title}</p>
          </div>
          <Pill tone={PRIORITY[t.priority].tone}>{PRIORITY[t.priority].label}</Pill>
        </Link>
      ))}
    </div>
  );
}

async function HandoffData({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  await connection();
  const [tasks, members] = await Promise.all([api.tasks().catch(() => null), api.members().catch(() => ({ items: [] }))]);
  if (!tasks) {
    return (
      <Notice tone="bad" role="alert">
        Không tải được yêu cầu bàn giao.
      </Notice>
    );
  }
  const queue = tasks.items.filter((t) => t.type === "human_request" && t.status !== "resolved" && t.status !== "cancelled");
  const wanted = typeof sp.task === "string" ? sp.task : undefined;
  const current = queue.find((t) => t.id === wanted) ?? queue[0];
  let call: CallDetail | null = null;
  if (current?.call_id) call = await api.call(current.call_id).catch(() => null);
  const aiSaid = call?.turns.filter((t) => t.speaker === "agent").slice(-2) ?? [];
  const customerSaid = call?.turns.filter((t) => t.speaker === "customer") ?? [];

  return (
    <div className="grid cols">
      <div className="grid">
        <Card title={current ? `Ngữ cảnh bàn giao · ${current.contact?.name ?? "Số lạ"}` : "Ngữ cảnh bàn giao"}>
          {!current ? (
            <div className="pad">
              <Empty>Chọn một yêu cầu trong hàng chờ.</Empty>
            </div>
          ) : (
            <div className="pad">
              <div className="actions" style={{ justifyContent: "space-between", marginBottom: 18 }}>
                <Pill tone="amber">Chưa xác minh danh tính</Pill>
                <Pill tone={TASK_STATUS[current.status].tone}>{TASK_STATUS[current.status].label}</Pill>
              </div>
              <div className="field">
                <label>Lý do chuyển</label>
                <p>{current.title}</p>
              </div>
              {current.description && (
                <div className="field">
                  <label>Tóm tắt của AI</label>
                  <p>{current.description}</p>
                </div>
              )}
              <div className="field">
                <label>Khách nói</label>
                {customerSaid.length ? customerSaid.map((t) => <p key={t.seq}>“{t.text}”</p>) : <p>Không có transcript.</p>}
              </div>
              <div className="field">
                <label>AI đã trao đổi</label>
                {aiSaid.length ? aiSaid.map((t) => <p key={t.seq}>{t.text}</p>) : <p>–</p>}
              </div>
              <div className="field">
                <label>Công cụ đã gọi</label>
                <p>
                  {call?.tool_runs.length
                    ? call.tool_runs.map((r) => `${r.tool} → ${handoffQueued(r.result) ? "đã xếp hàng, chưa có người nhận" : r.status}`).join(" · ")
                    : "Không có"}
                </p>
              </div>
              <div className="actions">
                {current.call_id && (
                  <Link className="link" href={`/cuoc-goi/${current.call_id}`}>
                    Xem transcript →
                  </Link>
                )}
                {current.contact && (
                  <Link className="link" href={`/khach-hang/${current.contact.id}`}>
                    Hồ sơ khách →
                  </Link>
                )}
              </div>
            </div>
          )}
        </Card>
      </div>
      <div className="grid">
        <Card title="Người nhận & xử lý tiếp">
          <div className="pad">
            {current ? (
              <HandoffActions
                members={members.items}
                callId={current.call_id}
                contactId={current.contact?.id ?? null}
                contactName={current.contact?.name ?? null}
              />
            ) : (
              <p>Không có yêu cầu đang chờ.</p>
            )}
          </div>
        </Card>
        <Card title={`Hàng chờ gặp nhân viên · ${queue.length}`}>
          <Queue tasks={queue} selected={current?.id} />
        </Card>
      </div>
    </div>
  );
}

export default function HandoffPage({ searchParams }: PageProps<"/ban-giao">) {
  return (
    <>
      <PageHead
        title="Bàn giao AI → nhân viên"
        sub="Khách yêu cầu gặp người thật: ngữ cảnh cuộc gọi, người nhận và đường gọi lại."
        actions={
          <Link className="btn" href="/hop-viec">
            Mở hộp việc
          </Link>
        }
      />
      <Suspense fallback={<Skeleton label="Đang tải bàn giao" />}>
        <HandoffData searchParams={searchParams} />
      </Suspense>
    </>
  );
}
