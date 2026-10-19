"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Icon } from "@/components/ui/Icon";
import { activeItem, NAV } from "@/lib/nav";

export type Viewer = { name: string; roleLabel: string; workspace: string; initials: string } | null;

export function Sidebar({ viewer }: { viewer: Viewer }) {
  const pathname = usePathname();
  return <SidebarView viewer={viewer} activeHref={activeItem(pathname)?.href} />;
}

/** Hook-free markup: also used as the static prerender fallback (no usePathname outside Suspense). */
export function SidebarView({ viewer, activeHref }: { viewer: Viewer; activeHref?: string }) {
  const active = activeHref ? { href: activeHref } : undefined;
  return (
    <aside>
      <Link className="logo" href="/">
        <span className="mark">≋</span>VoiceOS
        <span style={{ fontSize: 9, letterSpacing: 1, color: "#9aa2aa", margin: "8px 0 0 2px" }}>STUDIO</span>
      </Link>
      <div className="workspace">
        <span className="workicon">{viewer?.workspace.charAt(0) ?? "?"}</span>
        <div>
          <b>{viewer?.workspace ?? "Chưa đăng nhập"}</b>
          <span className="small">Workspace doanh nghiệp</span>
        </div>
      </div>
      <nav aria-label="Điều hướng chính">
        {NAV.map((item) => (
          <div key={item.href} style={{ display: "contents" }}>
            {item.group && <div className="navlabel">{item.group}</div>}
            <Link
              href={item.href}
              className={active?.href === item.href ? "active" : undefined}
              aria-current={active?.href === item.href ? "page" : undefined}
            >
              <span className="navicon">
                <Icon name={item.icon} />
              </span>
              {item.label}
            </Link>
          </div>
        ))}
      </nav>
      <div className="workspaceplan">
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <b>Ngân sách tháng</b>
          <span>chưa cấu hình</span>
        </div>
        <div className="track" aria-hidden="true">
          <i style={{ width: 0 }} />
        </div>
        <Link href="/chi-phi" style={{ color: "#7d9084" }}>
          Xem chi phí & sử dụng →
        </Link>
      </div>
      <div className="sidebarbottom">
        <span className="avatar">{viewer?.initials ?? "?"}</span>
        <div>
          <b>{viewer?.name ?? "Khách"}</b>
          <p>{viewer?.roleLabel ?? ""}</p>
        </div>
      </div>
    </aside>
  );
}
