"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type Item = { href: string; label: string; ready: boolean };

// Order and labels follow plan/template; items are enabled as their milestone lands (plan/docs/07).
const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: "Vận hành",
    items: [
      { href: "/", label: "Tổng quan", ready: true },
      { href: "/hop-viec", label: "Hộp việc cần xử lý", ready: false },
      { href: "/cuoc-goi", label: "Cuộc gọi", ready: false },
      { href: "/khach-hang", label: "Khách hàng", ready: true },
      { href: "/lich-hen", label: "Lịch hẹn & công việc", ready: false },
    ],
  },
  {
    title: "AI & dữ liệu",
    items: [
      { href: "/voice-spike", label: "Voice spike (M0.5)", ready: true },
      { href: "/agents", label: "Voice Agents", ready: false },
      { href: "/tri-thuc", label: "Kho tri thức", ready: false },
      { href: "/tu-dong-hoa", label: "Tự động hóa", ready: false },
    ],
  },
  {
    title: "Quản trị",
    items: [
      { href: "/sip", label: "Số điện thoại & SIP", ready: false },
      { href: "/cai-dat", label: "Cài đặt", ready: false },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <Link href="/" className="logo">
        ≋ VoiceOS
      </Link>
      <nav aria-label="Điều hướng chính">
        {GROUPS.map((g) => (
          <div key={g.title}>
            <div className="navgroup">{g.title}</div>
            {g.items.map((item) =>
              item.ready ? (
                <Link
                  key={item.href}
                  href={item.href}
                  className="navlink"
                  aria-current={pathname === item.href ? "page" : undefined}
                >
                  {item.label}
                </Link>
              ) : (
                <span key={item.href} className="navlink soon" aria-disabled="true">
                  {item.label} <span className="tag">sắp có</span>
                </span>
              ),
            )}
          </div>
        ))}
      </nav>
    </aside>
  );
}
