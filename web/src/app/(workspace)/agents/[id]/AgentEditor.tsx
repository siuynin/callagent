"use client";

import { useRouter } from "next/navigation";
import { useActionState, useEffect, useMemo, useState } from "react";

import {
  type AgentActionState,
  publishAction,
  rollbackAction,
  runEvalAction,
  saveDraftAction,
} from "@/app/actions/agents";
import { Card, DataTable, Empty, Notice, Pill } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/Toast";
import type { Agent, AgentConfig, AgentEval } from "@/lib/api";
import { submitTo } from "@/lib/forms";

const TABS = [
  ["general", "Thông tin & giọng"],
  ["flow", "Hội thoại"],
  ["tools", "Công cụ"],
  ["test", "Kiểm thử"],
  ["versions", "Phiên bản"],
] as const;
type Tab = (typeof TABS)[number][0];

const OPENAI_VOICES = ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"];
const TOOL_LABEL: Record<AgentConfig["tools"][number], [string, string]> = {
  check_available_slots: ["Kiểm tra lịch trống", "Tra khung giờ còn trống trước khi đề xuất."],
  create_appointment: ["Tạo lịch hẹn", "Chỉ chạy khi khách đã xác nhận ngày giờ, tên, số điện thoại."],
  request_handoff: ["Chuyển nhân viên", "Tạo yêu cầu trong Hộp việc; không phải chuyển máy trực tiếp."],
};
const VARS = ["{business_name}", "{greeting}", "{today}", "{weekday}", "{now_time}", "{timezone}"];
const INITIAL: AgentActionState = { ok: false };

function useNotify(state: AgentActionState) {
  const toast = useToast();
  useEffect(() => {
    if (state.at && state.message && state.ok) toast(state.message);
  }, [state, toast]);
}

function EvalPanel({ ev, live }: { ev: AgentEval | null | undefined; live: boolean }) {
  if (!ev) return <Empty>Bản nháp chưa được đánh giá.</Empty>;
  if (ev.status === "running")
    return (
      <Notice role="status">
        Đang chạy bộ đánh giá voice từ {ev.requested_at ? new Date(ev.requested_at).toLocaleTimeString("vi-VN") : "–"}. Trang tự
        cập nhật khi có kết quả.
      </Notice>
    );
  if (ev.status === "stale")
    return <Notice tone="bad">Đánh giá không báo kết quả sau 30 phút (gateway có thể đã dừng). Chạy lại.</Notice>;
  const s = ev.summary ?? {};
  const failedChecks = Object.entries(s.checks ?? {}).flatMap(([sc, checks]) => checks.map((c) => `${sc}: ${c.check}`));
  return (
    <div>
      <div className="actions" style={{ marginBottom: 14 }}>
        <Pill tone={ev.passed ? "green" : "red"}>{ev.passed ? "Đạt" : "Chưa đạt"}</Pill>
        {!live && !ev.valid_for_current_config && <Pill tone="amber">Đã sửa sau lần đánh giá này</Pill>}
        {s.note && <span className="small">{s.note}</span>}
      </div>
      {s.scenarios !== undefined && (
        <dl className="grid stats" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
          {[
            ["Kịch bản đạt", `${s.passed ?? 0}/${s.scenarios}`],
            ["Xác nhận sai", String(s.false_confirmations ?? 0)],
            ["p95 chậm nhất", s.worst_p95_ms ? `${Math.round(s.worst_p95_ms)} ms` : "–"],
            ["Nhà cung cấp", s.provider ?? "–"],
          ].map(([k, v]) => (
            <div key={k} className="card pad">
              <div className="statlabel">{k}</div>
              <div className="statvalue" style={{ fontSize: 20 }}>
                {v}
              </div>
            </div>
          ))}
        </dl>
      )}
      {failedChecks.length > 0 && (
        <div className="notice bad">
          <div>
            <b>Kiểm tra chưa đạt</b>
            {failedChecks.map((c) => (
              <div key={c}>· {c}</div>
            ))}
          </div>
        </div>
      )}
      {ev.error && <div className="notice bad">{ev.error}</div>}
    </div>
  );
}

export function AgentEditor({ agent, canEdit, canPublish }: { agent: Agent; canEdit: boolean; canPublish: boolean }) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("general");
  const base = (agent.draft_config ?? agent.active_config) as AgentConfig;
  const [config, setConfig] = useState<AgentConfig>(base);
  const dirty = useMemo(() => JSON.stringify(config) !== JSON.stringify(base), [config, base]);
  const set = <K extends keyof AgentConfig>(k: K, v: AgentConfig[K]) => setConfig((c) => ({ ...c, [k]: v }));

  const [saveState, save, saving] = useActionState(saveDraftAction, INITIAL);
  const [evalState, runEval, evaluating] = useActionState(runEvalAction, INITIAL);
  const [pubState, publish, publishing] = useActionState(publishAction, INITIAL);
  const [rbState, rollback, rollingBack] = useActionState(rollbackAction, INITIAL);
  useNotify(saveState);
  useNotify(evalState);
  useNotify(pubState);
  useNotify(rbState);
  const lastError = [saveState, evalState, pubState, rbState].filter((s) => !s.ok && s.message).sort((a, b) => (b.at ?? 0) - (a.at ?? 0))[0];
  const fieldErrors = saveState.ok ? {} : (saveState.fieldErrors ?? {});

  const draftEval = agent.draft?.eval;
  const running = draftEval?.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => router.refresh(), 5000);
    return () => clearInterval(t);
  }, [running, router]);

  const publishable =
    !!agent.draft && !dirty && draftEval?.status === "finished" && draftEval.passed === true && draftEval.valid_for_current_config;
  const publishHint = !agent.draft
    ? "Chưa có bản nháp"
    : dirty
      ? "Lưu bản nháp trước"
      : !draftEval || draftEval.status !== "finished"
        ? "Cần chạy đánh giá"
        : !draftEval.valid_for_current_config
          ? "Bản nháp đã sửa sau lần đánh giá, chạy lại"
          : !draftEval.passed
            ? "Bản nháp chưa đạt đánh giá"
            : "";

  return (
    <>
      <div className="actions" style={{ justifyContent: "flex-end", marginTop: -14, marginBottom: 16 }}>
        {dirty && <Pill tone="amber">Có thay đổi chưa lưu</Pill>}
        {canEdit && (
          <form onSubmit={submitTo(save)}>
            <input type="hidden" name="agent_id" value={agent.id} />
            <input type="hidden" name="agent_version" value={agent.version} />
            <input type="hidden" name="config" value={JSON.stringify(config)} />
            <button type="submit" disabled={saving || !dirty || running}>
              {saving ? "Đang lưu…" : "Lưu bản nháp"}
            </button>
          </form>
        )}
        {canPublish && (
          <form onSubmit={submitTo(publish)}>
            <input type="hidden" name="agent_id" value={agent.id} />
            <input type="hidden" name="version_id" value={agent.draft?.id ?? ""} />
            <button type="submit" className="primary" disabled={!publishable || publishing} title={publishHint}>
              {publishing ? "Đang xuất bản…" : agent.draft ? `Xuất bản v${agent.draft.number}` : "Xuất bản"}
            </button>
          </form>
        )}
      </div>
      {lastError?.message && (
        <Notice tone="bad" role="alert">
          {lastError.message}
        </Notice>
      )}
      {!canEdit && <Notice>Bạn đang xem ở chế độ chỉ đọc. Quản lý trở lên mới sửa được agent.</Notice>}
      <div className="tabs" role="tablist">
        {TABS.map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "active" : undefined} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "general" && (
        <Card title="Danh tính & giọng nói">
          <div className="pad formgrid">
            <div className="field">
              <label htmlFor="g-business">Tên doanh nghiệp (AI xưng)</label>
              <input id="g-business" value={config.business_name} disabled={!canEdit} onChange={(e) => set("business_name", e.target.value)} />
              {fieldErrors.business_name && <div className="fielderror">{fieldErrors.business_name}</div>}
            </div>
            <div className="field">
              <label htmlFor="g-provider">Nhà cung cấp model</label>
              <select
                id="g-provider"
                value={config.provider}
                disabled={!canEdit}
                onChange={(e) => {
                  const provider = e.target.value as AgentConfig["provider"];
                  setConfig((c) => ({ ...c, provider, voice: provider === "openai" ? "marin" : "" }));
                }}
              >
                <option value="openai">OpenAI Realtime</option>
                <option value="gemini">Gemini Live</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="g-voice">Giọng</label>
              {config.provider === "openai" ? (
                <select id="g-voice" value={config.voice} disabled={!canEdit} onChange={(e) => set("voice", e.target.value)}>
                  {OPENAI_VOICES.map((v) => (
                    <option key={v} value={v}>
                      {v}
                      {v === "marin" || v === "cedar" ? " (khuyến nghị)" : ""}
                    </option>
                  ))}
                </select>
              ) : (
                <input id="g-voice" value={config.voice} placeholder="Để trống = giọng mặc định" disabled={!canEdit} onChange={(e) => set("voice", e.target.value)} />
              )}
              <div className="small">Không đổi giọng được giữa cuộc gọi.</div>
            </div>
            <div className="field">
              <label htmlFor="g-vad">Chờ khách ngừng nói (ms)</label>
              <input
                id="g-vad"
                type="number"
                min={300}
                max={2000}
                step={50}
                value={config.vad_silence_ms}
                disabled={!canEdit}
                onChange={(e) => set("vad_silence_ms", Number(e.target.value))}
              />
              <div className="small">Ngắn quá dễ cắt ngang khách; dài quá AI trả lời chậm. Khuyến nghị 500–800.</div>
            </div>
            <div className="field full" style={{ gridColumn: "1 / -1" }}>
              <label htmlFor="g-greeting">Lời chào</label>
              <textarea id="g-greeting" style={{ minHeight: 80 }} value={config.greeting} disabled={!canEdit} onChange={(e) => set("greeting", e.target.value)} />
              {fieldErrors.greeting && <div className="fielderror">{fieldErrors.greeting}</div>}
              <div className="small">Bắt buộc nói rõ là trợ lý AI và thông báo ghi âm (kiểm tra khi xuất bản). Biến được dùng: {"{business_name}"}.</div>
            </div>
          </div>
        </Card>
      )}

      {tab === "flow" && (
        <Card title="Hướng dẫn hội thoại (prompt)" action={<span className="small">{config.instructions.length.toLocaleString("vi-VN")} ký tự</span>}>
          <div className="pad">
            <textarea
              aria-label="Hướng dẫn hội thoại"
              style={{ minHeight: 460, fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace", fontSize: 12 }}
              value={config.instructions}
              disabled={!canEdit}
              onChange={(e) => set("instructions", e.target.value)}
            />
            {fieldErrors.instructions && <div className="fielderror">{fieldErrors.instructions}</div>}
            <p className="small" style={{ marginTop: 8 }}>
              Biến được thay khi gọi: {VARS.join(" · ")}. Muốn viết dấu ngoặc nhọn thật thì gõ hai lần: {"{{ }}"}.
            </p>
          </div>
        </Card>
      )}

      {tab === "tools" && (
        <Card title="Công cụ được phép">
          <div className="pad">
            {(Object.keys(TOOL_LABEL) as AgentConfig["tools"]).map((t) => (
              <label key={t} className="radio">
                <input
                  type="checkbox"
                  checked={config.tools.includes(t)}
                  disabled={!canEdit}
                  onChange={(e) =>
                    set("tools", e.target.checked ? [...config.tools, t].sort() : config.tools.filter((x) => x !== t))
                  }
                />
                <span>
                  <b>{TOOL_LABEL[t][0]}</b>
                  <p>{TOOL_LABEL[t][1]}</p>
                </span>
              </label>
            ))}
            <p className="small">Model chỉ thấy công cụ được chọn; nếu vẫn tự gọi công cụ khác, gateway từ chối.</p>
          </div>
        </Card>
      )}

      {tab === "test" && (
        <div className="grid cols">
          <Card
            title={agent.draft ? `Đánh giá bản nháp v${agent.draft.number}` : "Đánh giá"}
            action={
              canEdit && agent.draft ? (
                <form onSubmit={submitTo(runEval)}>
                  <input type="hidden" name="agent_id" value={agent.id} />
                  <button type="submit" className="primary" disabled={evaluating || running || dirty}>
                    {running ? "Đang chạy…" : "▷ Chạy đánh giá"}
                  </button>
                </form>
              ) : null
            }
          >
            <div className="pad">
              {dirty && <Notice tone="warn">Lưu bản nháp trước; đánh giá chạy trên bản đã lưu.</Notice>}
              {agent.draft ? <EvalPanel ev={draftEval} live={false} /> : <Empty>Chưa có bản nháp. Sửa cấu hình rồi lưu để tạo bản nháp.</Empty>}
            </div>
          </Card>
          <Card title={agent.active_version ? `Phiên bản đang chạy v${agent.active_version.number}` : "Chưa xuất bản"}>
            <div className="pad">
              <EvalPanel ev={agent.active_version?.eval} live />
              <p className="small" style={{ marginTop: 12 }}>
                Ngưỡng: mọi kịch bản đạt, 0 xác nhận sai, p95 ≤ {config.eval_max_p95_ms} ms. Kịch bản lấy từ eval/scenarios (bỏ file mẫu bắt
                đầu bằng “_”).
              </p>
            </div>
          </Card>
        </div>
      )}

      {tab === "versions" && (
        <Card title="Lịch sử phiên bản">
          <DataTable heads={["Phiên bản", "Trạng thái", "Đánh giá", "Xuất bản lúc", ""]}>
            {(agent.versions ?? []).map((v) => (
              <tr key={v.id}>
                <td>
                  <b>v{v.number}</b>
                  {v.eval?.rolled_back_from && <small>chép từ v{v.eval.rolled_back_from}</small>}
                </td>
                <td>
                  {v.active ? (
                    <Pill tone="green">Đang hoạt động</Pill>
                  ) : v.status === "draft" ? (
                    <Pill tone="amber">Bản nháp</Pill>
                  ) : (
                    <Pill>Đã xuất bản</Pill>
                  )}
                </td>
                <td>{v.eval?.status === "finished" ? (v.eval.passed ? "Đạt" : "Chưa đạt") : v.eval?.status === "running" ? "Đang chạy" : "–"}</td>
                <td>{v.published_at ? new Date(v.published_at).toLocaleString("vi-VN") : "–"}</td>
                <td>
                  {canPublish && v.status === "published" && !v.active && (
                    <form onSubmit={submitTo(rollback)}>
                      <input type="hidden" name="agent_id" value={agent.id} />
                      <input type="hidden" name="version_id" value={v.id} />
                      <button type="submit" disabled={rollingBack}>
                        Quay lại bản này
                      </button>
                    </form>
                  )}
                </td>
              </tr>
            ))}
          </DataTable>
          <div className="foot">
            <span>Phiên bản đã xuất bản không sửa được; quay lại tạo một phiên bản mới chép từ bản cũ.</span>
          </div>
        </Card>
      )}
    </>
  );
}
