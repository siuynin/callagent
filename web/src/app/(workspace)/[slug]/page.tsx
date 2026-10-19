import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { Card, Notice, PageHead } from "@/components/ui/primitives";
import { NAV, navBySlug } from "@/lib/nav";

// Screens listed in the template navigation that are not ported yet. Honest placeholder: no fake
// controls that pretend to save anything (plan/docs/07 AC20).
const PENDING = NAV.filter((n) => !n.ready);

const MILESTONE: Record<string, string> = {
  "/hop-viec": "M1 · hộp việc, phân công, quá hạn",
  "/ban-giao": "M1 · bàn giao nhân viên và gọi lại",
  "/cuoc-goi": "M1 · lịch sử cuộc gọi, transcript, tool trace",
  "/lich-hen": "M1 · lịch hẹn và tài nguyên",
  "/agents": "M1 · phiên bản agent và bộ đánh giá voice",
  "/tri-thuc": "M1 · kho tri thức đã duyệt",
  "/danh-sach-goi": "M4 · danh sách gọi",
  "/chien-dich": "M4 · chiến dịch gọi ra (sau gate pháp lý)",
  "/tu-dong-hoa": "M2–M3 · quy tắc gọi tự động",
  "/tich-hop": "M3 · kết nối dữ liệu",
  "/sip": "Sau ADR 0004 · tổng đài và đầu số",
  "/bao-cao": "M1+ · báo cáo theo kết quả",
  "/chi-phi": "M1+ · usage và ngân sách",
  "/cai-dat": "M1 · thành viên, phân quyền, lịch làm việc",
};

export function generateStaticParams() {
  return PENDING.map((n) => ({ slug: n.href.slice(1) }));
}

export async function generateMetadata({ params }: PageProps<"/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  return { title: navBySlug(slug)?.label ?? "Không tìm thấy" };
}

// params read inside Suspense so client navigations stay instant (cacheComponents)
export default function PendingScreen({ params }: PageProps<"/[slug]">) {
  return (
    <Suspense fallback={<PageHead title="…" />}>
      <PendingContent params={params} />
    </Suspense>
  );
}

async function PendingContent({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const item = navBySlug(slug);
  if (!item || item.ready) notFound();
  return (
    <>
      <PageHead title={item.label} sub="Màn hình này đã có trong thiết kế, đang được port sang ứng dụng." />
      <Notice>
        Chưa có dữ liệu thật cho màn này. Thiết kế tham chiếu: <code>plan/template</code> · Dự kiến:{" "}
        {MILESTONE[item.href] ?? "theo backlog"}.
      </Notice>
      <Card title="Bạn có thể làm gì lúc này">
        <div className="pad portnote">
          <b>Các màn đã dùng được</b>
          {NAV.filter((n) => n.ready).map((n) => (
            <Link key={n.href} className="link" href={n.href}>
              {n.label} →
            </Link>
          ))}
        </div>
      </Card>
    </>
  );
}
