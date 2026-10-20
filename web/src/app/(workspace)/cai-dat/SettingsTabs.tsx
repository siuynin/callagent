import Link from "next/link";

const TABS = [
  { href: "/cai-dat", label: "Đội ngũ" },
  { href: "/cai-dat/lich-lam-viec", label: "Lịch làm việc & định tuyến" },
] as const;

export function SettingsTabs({ active }: { active: (typeof TABS)[number]["href"] }) {
  return (
    <div className="tabs" role="navigation" aria-label="Mục cài đặt">
      {TABS.map((t) => (
        <Link key={t.href} href={t.href} className={t.href === active ? "active" : undefined} aria-current={t.href === active ? "page" : undefined}>
          {t.label}
        </Link>
      ))}
      <button type="button" disabled title="Có ở các bước sau">
        Dữ liệu & bảo mật
      </button>
      <button type="button" disabled title="Có ở các bước sau">
        Nhật ký
      </button>
    </div>
  );
}
