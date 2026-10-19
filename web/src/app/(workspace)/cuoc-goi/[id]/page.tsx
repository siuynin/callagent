import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { Fragment, Suspense } from "react";

import { Card, Empty, Notice, PageHead, Pill, Skeleton, Stats } from "@/components/ui/primitives";
import { api, ApiError, type CallDetail } from "@/lib/api";
import { mmss, outcomeOf, TASK_STATUS, TASK_TYPE } from "@/lib/labels";

import { CreateTaskFromCall } from "./CallActions";

export const metadata: Metadata = { title: "Chi tiết cuộc gọi" };

const TOOL_LABEL: Record<string, string> = {
  check_available_slots: "Kiểm tra lịch trống",
  create_appointment: "Tạo lịch hẹn",
  request_handoff: "Chuyển nhân viên",
};

function at(ms: number) {
  return mmss(Math.max(0, Math.round(ms / 1000)));
}

function resultText(r: CallDetail["tool_runs"][number]) {
  const res = r.result ?? {};
  if (r.tool === "create_appointment" && res.appointment_id) return `${res.appointment_id} · thành công`;
  if (r.tool === "request_handoff" && res.handoff_status === "queued") return "đã xếp hàng, nhân viên CHƯA nhận";
  return r.status === "ok" ? "thành công" : r.status;
}

async function Detail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await connection();
  let detail: CallDetail;
  try {
    detail = await api.call(id);
  } catch (e) {
    if (e instanceof ApiError && [400, 404, 422].includes(e.status)) notFound();
    return (
      <Notice tone="bad" role="alert">
        Không tải được cuộc gọi.
      </Notice>
    );
  }
  const members = await api.members().catch(() => ({ items: [] }));
  const c = detail.data;
  const o = outcomeOf(c.business_outcome, c.technical_status);
  // merge transcript and tool events on one timeline (tool shown where it happened)
  const timeline = [
    ...detail.turns.map((t) => ({ kind: "turn" as const, ms: t.started_ms, turn: t })),
    ...detail.tool_runs.map((r) => ({ kind: "tool" as const, ms: r.started_ms, run: r })),
  ].sort((a, b) => a.ms - b.ms || (a.kind === "tool" ? 1 : -1));
  const started = new Date(c.started_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" });
  const handoffTask = detail.tasks.find((t) => t.type === "human_request" && t.status !== "resolved");

  return (
    <>
      {handoffTask && (
        <Notice>
          Khách yêu cầu người thật · Theo dõi tại màn hình bàn giao.{" "}
          <Link className="link" href={`/ban-giao?task=${handoffTask.id}`}>
            Mở bàn giao AI → nhân viên
          </Link>
        </Notice>
      )}
      <PageHead
        title={c.contact_name ?? "Số lạ"}
        sub={`Cuộc gọi ${c.direction === "inbound" ? "đến" : "đi"} · ${started}${c.after_hours ? " · ngoài giờ" : ""}`}
        actions={
          <>
            <Link className="btn" href="/cuoc-goi">
              ← Lịch sử
            </Link>
            <CreateTaskFromCall members={members.items} callId={c.id} contactId={c.contact_id} contactName={c.contact_name} />
          </>
        }
      />
      <Stats
        items={[
          { label: "Kết quả", value: o.label, foot: "Được AI phân loại · cần rà soát" },
          { label: "Thời lượng", value: mmss(c.duration_s), foot: "Agent: Lễ tân AI" },
          { label: "Chi phí AI", value: "–", foot: "Có khi gateway ghi usage vào backend (M1)" },
          { label: "Công việc liên quan", value: detail.tasks.length, foot: "Trong hộp việc" },
        ]}
      />
      <div className="grid cols">
        <Card title="Nội dung hội thoại" action={<span className="small">Bản ghi âm: chưa lưu ở M0</span>}>
          <div className="pad">
            {timeline.length === 0 ? (
              <Empty>{c.technical_status === "missed" ? "Cuộc gọi nhỡ, không có hội thoại." : "Không có transcript."}</Empty>
            ) : (
              <div className="chat">
                {timeline.map((e, i) =>
                  e.kind === "turn" ? (
                    <div key={i} className={`bubble${e.turn.speaker === "customer" ? " user" : ""}`}>
                      <small>
                        {e.turn.speaker === "customer" ? "Khách" : e.turn.speaker === "agent" ? "AI" : "Nhân viên"} · {at(e.ms)}
                      </small>
                      {e.turn.text}
                    </div>
                  ) : (
                    <div key={i} className="notice" style={{ margin: 0 }}>
                      ⌘ &nbsp; Công cụ: {TOOL_LABEL[e.run.tool] ?? e.run.tool} → {resultText(e.run)}
                    </div>
                  ),
                )}
              </div>
            )}
          </div>
        </Card>
        <div className="grid">
          <Card title="Tóm tắt & bước tiếp theo">
            <div className="pad">
              <h3>Kết quả</h3>
              <p style={{ marginBottom: 16 }}>
                <Pill tone={o.tone}>{o.label}</Pill>
              </p>
              <h3>Công việc liên quan</h3>
              {detail.tasks.length === 0 ? (
                <p>Chưa có công việc. Dùng “Tạo công việc” nếu cần theo dõi.</p>
              ) : (
                detail.tasks.map((t) => (
                  <p key={t.id} style={{ margin: "6px 0" }}>
                    <Link className="link" href="/hop-viec">
                      {TASK_TYPE[t.type]}
                    </Link>{" "}
                    · {t.title} · <Pill tone={TASK_STATUS[t.status].tone}>{TASK_STATUS[t.status].label}</Pill>
                  </p>
                ))
              )}
            </div>
          </Card>
          <Card title="Nguồn & nhật ký công cụ">
            <div className="pad">
              {detail.tool_runs.length === 0 ? (
                <p>Không gọi công cụ nào.</p>
              ) : (
                <div className="timeline">
                  {detail.tool_runs.map((r) => (
                    <Fragment key={r.seq}>
                      <div>
                        <b className="small">
                          {at(r.started_ms)} · {TOOL_LABEL[r.tool] ?? r.tool}
                        </b>
                        <p>
                          {r.tool} → {resultText(r)}
                        </p>
                      </div>
                    </Fragment>
                  ))}
                </div>
              )}
              {c.contact_id && (
                <Link className="link" href={`/khach-hang/${c.contact_id}`}>
                  Xem hồ sơ khách hàng →
                </Link>
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}

export default function CallDetailPage({ params }: PageProps<"/cuoc-goi/[id]">) {
  return (
    <Suspense fallback={<Skeleton label="Đang tải cuộc gọi" />}>
      <Detail params={params} />
    </Suspense>
  );
}
