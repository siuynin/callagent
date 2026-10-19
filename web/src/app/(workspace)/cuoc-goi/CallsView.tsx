"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { DataTable, Empty, Pill } from "@/components/ui/primitives";
import type { Call } from "@/lib/api";
import { mmss, outcomeOf } from "@/lib/labels";
import { fold } from "@/lib/text";

const DIRECTIONS = { all: "Tất cả", inbound: "Đến", outbound: "Đi" } as const;

export function CallsView({ calls }: { calls: Call[] }) {
  const [query, setQuery] = useState("");
  const [direction, setDirection] = useState<keyof typeof DIRECTIONS>("all");
  const rows = useMemo(() => {
    const q = fold(query.trim());
    return calls.filter(
      (c) => (direction === "all" || c.direction === direction) && (!q || fold(c.contact_name ?? "").includes(q)),
    );
  }, [calls, query, direction]);

  return (
    <>
      <div className="tabs">
        <button type="button" className="active">
          Lịch sử cuộc gọi
        </button>
        <button type="button" disabled title="Có khi tổng đài thật chạy (M1)">
          Đang diễn ra
        </button>
      </div>
      <div className="toolbar">
        <input aria-label="Tìm cuộc gọi" placeholder="⌕  Tìm tên khách…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select aria-label="Lọc hướng gọi" value={direction} onChange={(e) => setDirection(e.target.value as keyof typeof DIRECTIONS)}>
          {Object.entries(DIRECTIONS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <span className="small right">{rows.length} cuộc gọi</span>
      </div>
      <section className="card">
        {rows.length === 0 ? (
          <div className="pad">
            <Empty>{calls.length ? "Không có cuộc gọi khớp bộ lọc." : "Chưa có cuộc gọi nào."}</Empty>
          </div>
        ) : (
          <>
            <DataTable heads={["Khách hàng", "Hướng", "Agent", "Kết quả", "Thời lượng", "Thời điểm", ""]} responsive>
              {rows.map((c) => {
                const o = outcomeOf(c.business_outcome, c.technical_status);
                return (
                  <tr key={c.id}>
                    <td>
                      <Link className="link" href={`/cuoc-goi/${c.id}`}>
                        {c.contact_name ?? "Số lạ"}
                      </Link>
                      {c.after_hours && <small>Ngoài giờ làm việc</small>}
                    </td>
                    <td>{c.direction === "inbound" ? "↙ Đến" : "↗ Đi"}</td>
                    <td>Lễ tân AI</td>
                    <td>
                      <Pill tone={o.tone}>{o.label}</Pill>
                    </td>
                    <td>{mmss(c.duration_s)}</td>
                    <td>{new Date(c.started_at).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}</td>
                    <td>
                      <Link className="btn" href={`/cuoc-goi/${c.id}`} aria-label={`Mở cuộc gọi của ${c.contact_name ?? "số lạ"}`}>
                        ↗
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </DataTable>
            <ul className="cardlist">
              {rows.map((c) => {
                const o = outcomeOf(c.business_outcome, c.technical_status);
                return (
                  <li key={c.id} className="card">
                    <div className="row">
                      <Link className="link" href={`/cuoc-goi/${c.id}`}>
                        {c.contact_name ?? "Số lạ"}
                      </Link>
                      <Pill tone={o.tone}>{o.label}</Pill>
                    </div>
                    <p>
                      {c.direction === "inbound" ? "↙ Đến" : "↗ Đi"} · {mmss(c.duration_s)} ·{" "}
                      {new Date(c.started_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Ho_Chi_Minh" })}
                    </p>
                  </li>
                );
              })}
            </ul>
          </>
        )}
        <div className="foot">
          <span>Dữ liệu dev · cuộc gọi từ provider mock-seed là dữ liệu tổng hợp</span>
          <span>Tối đa 100 cuộc gần nhất</span>
        </div>
      </section>
    </>
  );
}
