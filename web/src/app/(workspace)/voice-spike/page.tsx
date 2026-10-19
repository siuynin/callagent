import type { Metadata } from "next";

import { Card, Notice, PageHead } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Voice spike" };

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://127.0.0.1:8100";

const STEPS = [
  ["Điền key", "GEMINI_API_KEY và/hoặc OPENAI_API_KEY trong voiceos/.env. Không dán key vào chat."],
  ["Kiểm tra nhanh", "python -m gateway.smoke --provider openai (hoặc gemini): xác nhận key, model, cấu hình."],
  ["Gọi thử bằng micro", "Chọn nhà cung cấp trên trang gọi thử, thử đặt lịch, đọc số điện thoại, hỏi trả góp, chen ngang."],
  ["Mô phỏng đường điện thoại", "Bật 8 kHz G.711 để đo chất lượng nhận dạng ở băng thông thoại."],
  ["Đánh giá lặp lại", "Ghi âm kịch bản trong eval/, chạy eval_runner cho từng provider và so sánh."],
];

export default function VoiceSpikePage() {
  return (
    <>
      <PageHead
        title="Voice spike (M0.5)"
        sub="Đo độ trễ, ngắt lời, công cụ và xác nhận sai của lễ tân AI trước gate G-V."
        actions={
          <a className="btn primary" href={GATEWAY_URL} target="_blank" rel="noreferrer">
            Mở trang gọi thử ↗
          </a>
        }
      />
      <Notice>
        Trang gọi thử chạy trên media gateway (127.0.0.1) để API key của model chỉ nằm ở backend. Báo cáo từng cuộc
        lưu trong media-gateway/reports.
      </Notice>
      <Card title="Quy trình đo">
        <div className="pad timeline" style={{ margin: 24 }}>
          {STEPS.map(([title, body]) => (
            <div key={title}>
              <h3>{title}</h3>
              <p>{body}</p>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
