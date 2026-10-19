import { connection } from "next/server";
import Link from "next/link";
import { Suspense } from "react";

import { api, type Health } from "@/lib/api";

async function SystemStatus() {
  await connection();
  let h: Health | null = null;
  try {
    h = await api.health();
  } catch {
    h = null;
  }
  if (!h) return <p className="muted">Chưa đọc được trạng thái hệ thống.</p>;
  const rows: [string, string][] = [
    ["API", h.status === "ok" ? "Hoạt động" : h.status],
    ["Môi trường", h.env],
    ["Tổng đài", h.modes.call_provider === "mock" ? "Giả lập" : h.modes.call_provider],
    ["Gọi ra", h.modes.outbound_enabled ? "Đang bật" : "Đang tắt"],
  ];
  return (
    <dl className="grid">
      {rows.map(([k, v]) => (
        <div key={k} className="card stat">
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function OverviewPage() {
  return (
    <>
      <header className="pagehead">
        <h1>Tổng quan</h1>
        <p className="muted">
          Nền tảng M0 đang dựng. KPI vận hành (cuộc gọi nhỡ được xử lý, lịch hẹn ngoài giờ, speed-to-lead) xuất hiện
          khi M1 có dữ liệu cuộc gọi thật.
        </p>
      </header>
      <Suspense fallback={<div className="skeleton" aria-label="Đang tải" />}>
        <SystemStatus />
      </Suspense>
      <section className="card" style={{ marginTop: 16 }}>
        <h2>Việc tiếp theo</h2>
        <p>
          Chạy <Link href="/voice-spike">voice spike</Link> để đo độ trễ, khả năng ngắt lời và chi phí của Gemini Live
          bằng tiếng Việt trước khi mở rộng phạm vi (gate G-V).
        </p>
      </section>
    </>
  );
}
