import type { Metadata } from "next";

export const metadata: Metadata = { title: "Voice spike" };

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://127.0.0.1:8100";

export default function VoiceSpikePage() {
  return (
    <>
      <header className="pagehead">
        <h1>Voice spike (M0.5)</h1>
        <p className="muted">
          Gọi thử lễ tân AI bằng micro, đo độ trễ, ngắt lời, công cụ và xác nhận sai. Trang gọi chạy trên media
          gateway để API key của model chỉ nằm ở backend.
        </p>
      </header>
      <section className="card">
        <h2>Cách chạy</h2>
        <ol>
          <li>Điền GEMINI_API_KEY và AI_PROVIDER=gemini trong voiceos/.env (để mock nếu chỉ thử giao diện).</li>
          <li>Khởi động gateway (xem README), rồi mở trang gọi thử.</li>
          <li>Bật &quot;Mô phỏng đường điện thoại 8 kHz&quot; để đo chất lượng ở băng thông thoại.</li>
          <li>Báo cáo từng cuộc nằm trong media-gateway/reports; bộ đánh giá lặp lại được ở thư mục eval.</li>
        </ol>
        <a className="button" href={GATEWAY_URL} target="_blank" rel="noreferrer">
          Mở trang gọi thử
        </a>
      </section>
    </>
  );
}
