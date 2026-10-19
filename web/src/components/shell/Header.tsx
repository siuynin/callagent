"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { activeItem, NAV } from "@/lib/nav";
import { fold } from "@/lib/text";

export function Header({ initials, envLabel }: { initials: string; envLabel: string | null }) {
  const pathname = usePathname();
  const router = useRouter();
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const crumb = activeItem(pathname)?.label ?? "Trang";

  // template behaviour: body.navopen slides the sidebar in on mobile; close it on every navigation
  useEffect(() => {
    document.body.classList.remove("navopen");
  }, [pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const results = NAV.filter((n) => fold(n.label).includes(fold(query.trim())));

  return (
    <header>
      <div className="actions">
        <button
          type="button"
          className="mobilebtn"
          aria-label="Mở menu"
          onClick={() => document.body.classList.toggle("navopen")}
        >
          ☰
        </button>
        <span className="breadcrumb">
          Workspace &nbsp;/&nbsp; <b>{crumb}</b>
        </span>
      </div>
      <div className="topright">
        <button type="button" className="topsearch" onClick={() => setSearchOpen(true)}>
          ⌕ &nbsp; Tìm màn hình <kbd>⌘ K</kbd>
        </button>
        {envLabel && <span className="pill amber">{envLabel}</span>}
        <Link className="flat topbell" aria-label="Yêu cầu cần xử lý" href="/hop-viec">
          ♧
        </Link>
        <span className="avatar">{initials}</span>
      </div>
      {searchOpen && (
        <Modal
          title="Đi đến màn hình"
          onClose={() => {
            setSearchOpen(false);
            setQuery("");
          }}
        >
          <input
            aria-label="Tìm màn hình"
            placeholder="Tìm cuộc gọi, khách hàng, tự động hóa…"
            style={{ width: "100%" }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && results[0]) {
                setSearchOpen(false);
                router.push(results[0].href);
              }
            }}
          />
          <div style={{ marginTop: 15, display: "grid", gap: 4 }}>
            {results.map((n) => (
              <Link key={n.href} className="link" href={n.href} onClick={() => setSearchOpen(false)}>
                {n.label}
                {!n.ready && <span className="small"> · đang port</span>}
              </Link>
            ))}
            {!results.length && <p>Không có màn hình phù hợp.</p>}
          </div>
        </Modal>
      )}
    </header>
  );
}

/** Static header for the prerendered shell; the interactive Header replaces it once data streams in. */
export function HeaderPlaceholder() {
  return (
    <header>
      <div className="actions">
        <span className="breadcrumb">Workspace</span>
      </div>
      <div className="topright">
        <span className="avatar" aria-hidden="true" />
      </div>
    </header>
  );
}
