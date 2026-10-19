"use client";

import Link from "next/link";
import { useActionState, useState } from "react";

import { type AgentActionState, createAgentAction } from "@/app/actions/agents";
import { Modal } from "@/components/ui/Modal";
import { Empty, Pill } from "@/components/ui/primitives";
import type { Agent } from "@/lib/api";
import { submitTo } from "@/lib/forms";

const PROVIDER: Record<string, string> = { openai: "OpenAI Realtime", gemini: "Gemini Live" };
const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://127.0.0.1:8100";

function evalLabel(a: Agent): string {
  const e = a.active_version?.eval;
  if (!e) return "–";
  if (e.summary?.note) return "Khởi tạo";
  return e.passed ? `${e.summary?.passed ?? 0}/${e.summary?.scenarios ?? 0}` : "Chưa đạt";
}

export function AgentsView({ agents, canCreate }: { agents: Agent[]; canCreate: boolean }) {
  const [creating, setCreating] = useState(false);
  return (
    <>
      {canCreate && (
        <div className="toolbar">
          <div className="right">
            <button type="button" className="primary" onClick={() => setCreating(true)}>
              + Tạo agent
            </button>
          </div>
        </div>
      )}
      {agents.length === 0 ? (
        <Empty>Chưa có agent nào.</Empty>
      ) : (
        <div className="grid agentgrid">
          {agents.map((a) => (
            <section key={a.id} className="card pad">
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <div className="agenticon" aria-hidden="true">
                  ≋
                </div>
                {a.active_version ? <Pill tone="green">Hoạt động · v{a.active_version.number}</Pill> : <Pill>Bản nháp</Pill>}
              </div>
              <h2>{a.name}</h2>
              <p style={{ margin: "10px 0 18px", minHeight: 36 }}>{a.description ?? "Chưa có mô tả."}</p>
              <span className="pill">Tiếng Việt</span> <span className="pill">{PROVIDER[a.provider ?? ""] ?? "Chưa chọn"}</span>
              {a.draft && (
                <>
                  {" "}
                  <Pill tone="amber">Có bản nháp v{a.draft.number}</Pill>
                </>
              )}
              <div className="agentmeta">
                <span>
                  <b>{a.calls_today}</b>Cuộc gọi hôm nay
                </span>
                <span>
                  <b>{evalLabel(a)}</b>Đạt kiểm thử
                </span>
              </div>
              <div className="actions" style={{ marginTop: 22 }}>
                <Link className="btn primary" href={`/agents/${a.id}`}>
                  Cấu hình
                </Link>
                <a className="btn" href={GATEWAY_URL} target="_blank" rel="noreferrer">
                  Gọi thử
                </a>
              </div>
            </section>
          ))}
        </div>
      )}
      <div className="annotation">
        Luồng: sửa bản nháp → chạy bộ đánh giá voice → xuất bản (chỉ khi đạt) → cuộc gọi mới dùng phiên bản đó. Có thể quay
        lại phiên bản cũ bất cứ lúc nào.
      </div>
      {creating && <CreateAgentModal onClose={() => setCreating(false)} />}
    </>
  );
}

const INITIAL: AgentActionState = { ok: false };

function CreateAgentModal({ onClose }: { onClose: () => void }) {
  const [state, action, pending] = useActionState(createAgentAction, INITIAL);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  return (
    <Modal
      title="Tạo agent"
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose}>
            Hủy
          </button>
          <button type="submit" form="createagent" className="primary" disabled={pending}>
            {pending ? "Đang tạo…" : "Tạo agent"}
          </button>
        </>
      }
    >
      <form id="createagent" onSubmit={submitTo(action)} noValidate>
        <div className="field">
          <label htmlFor="a-name">Tên agent *</label>
          <input id="a-name" name="name" value={name} onChange={(e) => setName(e.target.value)} />
          {state.fieldErrors?.name && <div className="fielderror">{state.fieldErrors.name}</div>}
        </div>
        <div className="field">
          <label htmlFor="a-desc">Mô tả</label>
          <input id="a-desc" name="description" value={description} onChange={(e) => setDescription(e.target.value)} />
          <div className="small">Agent mới bắt đầu bằng bản nháp từ mẫu lễ tân; cần đạt đánh giá mới xuất bản được.</div>
        </div>
        {state.message && (
          <div className="fielderror" role="alert">
            {state.message}
          </div>
        )}
      </form>
    </Modal>
  );
}
