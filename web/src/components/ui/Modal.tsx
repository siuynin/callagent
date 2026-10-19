"use client";

import { type ReactNode, useEffect, useRef } from "react";

// Markup and classes from the template's modal(); adds Escape, initial focus and focus restore.
export function Modal({
  title,
  onClose,
  children,
  footer,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    // first form field, not the header's close button (which comes first in DOM order)
    const dialog = dialogRef.current;
    const first =
      dialog?.querySelector<HTMLElement>("input:not([type=hidden]), select, textarea") ??
      dialog?.querySelector<HTMLElement>(".modalbody button, .modalfoot button, button");
    first?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab" && dialogRef.current) {
        const items = dialogRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (!items.length) return;
        const firstItem = items[0];
        const lastItem = items[items.length - 1];
        if (e.shiftKey && document.activeElement === firstItem) {
          e.preventDefault();
          lastItem.focus();
        } else if (!e.shiftKey && document.activeElement === lastItem) {
          e.preventDefault();
          firstItem.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose]);

  return (
    <div className="overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} ref={dialogRef}>
        <div className="modalhead">
          <h2>{title}</h2>
          <button type="button" className="flat" aria-label="Đóng" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="modalbody">{children}</div>
        {footer && <div className="modalfoot">{footer}</div>}
      </div>
    </div>
  );
}
