import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";

import { Icon } from "@/components/ui/Icon";
import { Card, DataTable, Empty, PageHead, Pill, Skeleton, Stats } from "@/components/ui/primitives";
import { api, type Call, type Health, type Me } from "@/lib/api";

const HERO_BARS = [17, 32, 49, 62, 40, 25, 44, 20];

async function Greeting() {
  await connection();
  const me = await api.me().catch((): Me | null => null);
  const tz = me?.tenant.timezone ?? "Asia/Ho_Chi_Minh";
  const today = new Intl.DateTimeFormat("vi-VN", { day: "numeric", month: "long", year: "numeric", timeZone: tz }).format(
    new Date(),
  );
  const first = me?.display_name.trim().split(/\s+/).at(-1);
  return (
    <PageHead
      title={first ? `Chào ${first}, một ngày làm việc hiệu quả 👋` : "Tổng quan"}
      sub="Đây là những gì đang diễn ra tại không gian làm việc của bạn."
      actions={
        <>
          <span className="pill">{today}</span>
          <Link className="btn primary" href="/voice-spike">
            ↗ Gọi thử agent
          </Link>
        </>
      }
    />
  );
}

async function Kpis() {
  await connection();
  const [contacts, calls] = await Promise.all([
    api.contacts().catch(() => null),
    api.calls().catch(() => null),
  ]);
  const callCount = calls ? `${calls.items.length}${calls.next_cursor ? "+" : ""}` : "–";
  return (
    <Stats
      items={[
        { label: "Cuộc gọi", value: callCount, foot: calls?.items.length ? "gần nhất" : "Chưa có cuộc gọi nào" },
        { label: "Kết nối gọi đi", value: "–", foot: "Gọi ra đang tắt (gate pháp lý)" },
        { label: "Lịch hẹn được tạo", value: "–", foot: "Có từ M1 (lễ tân AI)" },
        {
          label: "Khách hàng",
          value: contacts ? `${contacts.items.length}${contacts.next_cursor ? "+" : ""}` : "–",
          foot: "trong workspace",
        },
      ]}
    />
  );
}

const DIRECTION: Record<Call["direction"], string> = { inbound: "↙ Đến", outbound: "↗ Đi" };

async function RecentCalls() {
  await connection();
  const calls = await api.calls().catch(() => null);
  if (!calls) return <Empty>Không tải được cuộc gọi.</Empty>;
  if (!calls.items.length)
    return (
      <div className="pad">
        <Empty>Chưa có cuộc gọi. Cuộc gọi qua tổng đài thật sẽ xuất hiện ở đây từ M1.</Empty>
      </div>
    );
  return (
    <DataTable heads={["Hướng", "Bắt đầu", "Trạng thái", "Kết quả"]}>
      {calls.items.map((c) => (
        <tr key={c.id}>
          <td>{DIRECTION[c.direction]}</td>
          <td>{new Date(c.started_at).toLocaleString("vi-VN")}</td>
          <td>{c.technical_status}</td>
          <td>{c.business_outcome ? <Pill tone="green">{c.business_outcome}</Pill> : "–"}</td>
        </tr>
      ))}
    </DataTable>
  );
}

async function SystemStatus() {
  await connection();
  const h = await api.health().catch((): Health | null => null);
  const rows: [string, string, number, string][] = h
    ? [
        ["API", h.status === "ok" ? "Hoạt động" : h.status, 100, "#329779"],
        ["Tổng đài", h.modes.call_provider === "mock" ? "Giả lập" : h.modes.call_provider, 40, "#dfc49e"],
        ["Kết nối dữ liệu", h.modes.connector_mode === "mock" ? "Giả lập" : "Thật", 40, "#dfc49e"],
        ["Gọi ra", h.modes.outbound_enabled ? "Đang bật" : "Đang tắt", 100, "#9ab9d5"],
      ]
    : [];
  if (!rows.length) return <div className="pad"><Empty>Chưa đọc được trạng thái hệ thống.</Empty></div>;
  return (
    <div className="pad">
      {rows.map(([label, value, width, color]) => (
        <div key={label} className="metricrow">
          <label>{label}</label>
          <div className="track">
            <i style={{ width: `${width}%`, background: color }} />
          </div>
          <b style={{ minWidth: 70, textAlign: "right", fontWeight: 550 }}>{value}</b>
        </div>
      ))}
      <p className="small">Môi trường: {h?.env}</p>
    </div>
  );
}

const QUICK = [
  { href: "/khach-hang", icon: "customers", title: "Quản lý khách hàng", sub: "Thêm, tra cứu, cập nhật hồ sơ" },
  { href: "/voice-spike", icon: "spike", title: "Đo chất lượng lễ tân AI", sub: "So sánh Gemini và OpenAI" },
  { href: "/hop-viec", icon: "inbox", title: "Hộp việc cần xử lý", sub: "Phân công, quá hạn, kết quả" },
] as const;

export default function OverviewPage() {
  return (
    <>
      <Suspense fallback={<PageHead title="Tổng quan" sub="Đây là những gì đang diễn ra tại không gian làm việc của bạn." />}>
        <Greeting />
      </Suspense>
      <section className="hero">
        <div>
          <small>YOUR AI TEAM, ALWAYS READY</small>
          <h2>Mỗi cuộc gọi, một cơ hội kết nối.</h2>
          <p>Trợ lý AI tiếp nhận khách hàng. Đội ngũ của bạn tập trung vào những cuộc trò chuyện quan trọng.</p>
          <Link className="btn" href="/voice-spike">
            Gọi thử lễ tân AI &nbsp; →
          </Link>
        </div>
        <div className="hero-orb" aria-hidden="true">
          {HERO_BARS.map((h, i) => (
            <i key={i} style={{ height: h }} />
          ))}
        </div>
      </section>
      <Suspense fallback={<Skeleton label="Đang tải chỉ số" />}>
        <Kpis />
      </Suspense>
      <div className="dash-quick">
        {QUICK.map((q) => (
          <Link key={q.href} className="quick" href={q.href}>
            <span className="qicon">
              <Icon name={q.icon} />
            </span>
            <div>
              <b>{q.title}</b>
              <p>{q.sub}</p>
            </div>
            <span aria-hidden="true">→</span>
          </Link>
        ))}
      </div>
      <div className="grid cols">
        <Card title="Cuộc gọi gần đây" action={<Link className="link" href="/cuoc-goi">Xem tất cả →</Link>}>
          <Suspense fallback={<Skeleton label="Đang tải cuộc gọi" />}>
            <RecentCalls />
          </Suspense>
        </Card>
        <Card title="Trạng thái hệ thống">
          <Suspense fallback={<Skeleton label="Đang tải trạng thái" />}>
            <SystemStatus />
          </Suspense>
        </Card>
      </div>
    </>
  );
}
