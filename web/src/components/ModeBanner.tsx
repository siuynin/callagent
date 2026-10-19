import { connection } from "next/server";

import { api, type Health } from "@/lib/api";

// Simulated behaviour must always be labelled (plan/START_HERE_AGENT.md).
export async function ModeBanner() {
  await connection();
  let modes: Health["modes"] | null = null;
  try {
    modes = (await api.health()).modes;
  } catch {
    modes = null;
  }
  if (!modes) {
    return (
      <div className="banner bad" role="alert">
        Không kết nối được API. Kiểm tra backend đang chạy ở API_ORIGIN.
      </div>
    );
  }
  const parts = [
    modes.call_provider === "mock" && "tổng đài giả lập",
    modes.connector_mode === "mock" && "kết nối dữ liệu giả lập",
    modes.notify_provider === "mock" && "thông báo giả lập",
    !modes.outbound_enabled && "gọi ra đang tắt",
  ].filter(Boolean);
  if (!parts.length) return null;
  return (
    <div className="banner warn" role="status">
      Chế độ thử nghiệm: {parts.join(" · ")}.
    </div>
  );
}
