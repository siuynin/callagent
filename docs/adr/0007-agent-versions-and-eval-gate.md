# ADR 0007 · Phiên bản agent và cổng eval trước khi xuất bản
Trạng thái: Đã chấp nhận · 19/10/2026

## Bối cảnh
Prompt và cấu hình voice agent quyết định agent nói gì với khách. Sửa prompt có thể làm agent xác nhận sai lịch hẹn hoặc bỏ câu thông báo AI/ghi âm. Plan yêu cầu mỗi cuộc gọi truy được về đúng phiên bản đã chạy (AC04), và chỉ xuất bản khi bộ eval giọng nói đạt (AC25). Trước đây prompt nằm trong file của gateway, đổi là phải deploy.

## Quyết định
- Cấu hình agent là `AgentConfig` (backend `voiceos/agents/config.py`): instructions, greeting, business_name, provider, voice, tools, vad_silence_ms, eval_max_p95_ms. Prompt chỉ được dùng biến trong danh sách trắng (`business_name`, `today`, `weekday`, `now_time`, `timezone`, `greeting`); greeting chỉ dùng `{business_name}`.
- Mỗi agent có một bản nháp và các phiên bản đã xuất bản, đánh số tăng dần, không sửa lại. `agent.active_version_id` trỏ tới phiên bản đang chạy. Sửa bản nháp dùng If-Match theo `agent.version`.
- Eval gắn với `config_hash` của bản nháp. Sửa bản nháp đổi hash nên kết quả cũ hết hiệu lực. Backend gọi gateway `POST /internal/eval`, gateway chạy bộ kịch bản với model thật rồi gửi kết quả về `POST /internal/agent-versions/{id}/eval-result`; kết quả có hash cũ hoặc cho phiên bản không còn là nháp bị bỏ qua. Lần chạy treo quá 30 phút hiển thị "quá hạn".
- Đạt eval: mọi kịch bản pass, 0 lần xác nhận sai, p95 kém nhất không vượt `eval_max_p95_ms`, bộ kịch bản không rỗng.
- Xuất bản (chỉ admin): cần eval đạt cho đúng hash hiện tại và greeting phải có câu thông báo AI và "ghi âm" (`COMPLIANCE_GREETING`, `EVAL_REQUIRED`).
- Rollback tạo một phiên bản mới là bản sao của phiên bản cũ, giữ nguyên lịch sử.
- Gateway lấy phiên bản đang chạy qua `GET /internal/agents/active` (không bao giờ lấy bản nháp), ghi `agent_version_id` vào cuộc gọi, và chặn tool ngoài danh sách cho phép của phiên bản. Backend không với tới được thì gateway dùng prompt trong file (ghi `source=file` trong summary).

## Hệ quả
- Mỗi lần eval tốn tiền model thật (khoảng 2–3 phút cho bộ hiện tại). Gateway chỉ chạy một eval một lúc (409 khi bận).
- Seed tạo sẵn v1 với kết quả eval "bootstrap" để môi trường dev chạy được ngay; tenant thật phải chạy eval trước lần xuất bản đầu.
- Bộ kịch bản eval còn nhỏ (2 kịch bản). Cần mở rộng trước khi coi cổng này là đủ cho khách thật.
