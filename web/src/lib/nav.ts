import type { IconName } from "@/components/ui/Icon";

export type NavItem = {
  href: string;
  label: string;
  icon: IconName;
  group?: string;
  /** false: screen not ported from plan/template yet (shows an honest placeholder) */
  ready: boolean;
};

// Order, groups and labels follow plan/template (navs in app.js); routes use Vietnamese slugs.
export const NAV: NavItem[] = [
  { group: "VẬN HÀNH", href: "/", label: "Tổng quan", icon: "overview", ready: true },
  { href: "/hop-viec", label: "Hộp việc cần xử lý", icon: "inbox", ready: true },
  { href: "/danh-sach-goi", label: "Danh sách gọi", icon: "diallists", ready: false },
  { href: "/ban-giao", label: "Bàn giao nhân viên", icon: "handoff", ready: true },
  { href: "/cuoc-goi", label: "Cuộc gọi", icon: "calls", ready: true },
  { href: "/khach-hang", label: "Khách hàng", icon: "customers", ready: true },
  { href: "/lich-hen", label: "Lịch hẹn & công việc", icon: "tasks", ready: false },
  { group: "AI & DỮ LIỆU", href: "/agents", label: "Voice Agents", icon: "agents", ready: true },
  { href: "/tri-thuc", label: "Kho tri thức", icon: "knowledge", ready: false },
  { href: "/chien-dich", label: "Chiến dịch gọi", icon: "campaigns", ready: false },
  { href: "/tu-dong-hoa", label: "Tự động hóa", icon: "automations", ready: false },
  { href: "/tich-hop", label: "Tích hợp bên thứ ba", icon: "integrations", ready: false },
  { href: "/voice-spike", label: "Voice spike (M0.5)", icon: "spike", ready: true },
  { group: "QUẢN TRỊ", href: "/sip", label: "Số điện thoại & SIP", icon: "sip", ready: false },
  { href: "/bao-cao", label: "Báo cáo", icon: "reports", ready: false },
  { href: "/chi-phi", label: "Chi phí & sử dụng", icon: "billing", ready: false },
  { href: "/cai-dat", label: "Cài đặt", icon: "settings", ready: true },
];

/** Nav item that owns a pathname (detail pages highlight their list page, like the template). */
export function activeItem(pathname: string): NavItem | undefined {
  if (pathname === "/") return NAV[0];
  return NAV.filter((n) => n.href !== "/" && (pathname === n.href || pathname.startsWith(n.href + "/"))).at(0);
}

export function navBySlug(slug: string): NavItem | undefined {
  return NAV.find((n) => n.href === `/${slug}`);
}
