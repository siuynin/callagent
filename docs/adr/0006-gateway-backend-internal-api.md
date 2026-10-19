# ADR 0006 · Gateway ghi cuộc gọi vào backend qua API nội bộ
Trạng thái: Đã chấp nhận · 19/10/2026

## Bối cảnh
Cuộc gọi qua media gateway (voice spike, sau này là tổng đài thật) phải xuất hiện trong ứng dụng: lịch sử cuộc gọi, transcript, tool trace, hộp việc. Yêu cầu khách gặp nhân viên phải thành việc thật, tối đa một việc mỗi cuộc gọi (AC07), và agent không được nói "đã chuyển yêu cầu" khi hệ thống chưa ghi nhận (AC21).

## Quyết định
- Backend có nhóm route `/api/v1/internal/*` (không có trong OpenAPI công khai), xác thực bằng `X-Service-Token` (so khớp hằng thời gian) và `X-Tenant-Id` bắt buộc, tenant phải tồn tại. Token người dùng không vào được route nội bộ, token dịch vụ không vào được route người dùng. Thiếu `GATEWAY_SERVICE_TOKEN` thì route trả 503.
- Endpoint, tất cả idempotent:
  - `POST /internal/calls`: khóa theo (tenant, provider, provider_call_id); gắn khách chỉ khi số gọi đến khớp đúng một khách (AC03).
  - `POST /internal/calls/{id}/turns`: bỏ qua seq đã có.
  - `POST /internal/calls/{id}/tool-runs`: bỏ qua idempotency_key đã có.
  - `POST /internal/calls/{id}/handoff`: tạo việc `human_request` ưu tiên cao, hạn 15 phút, `source_key = handoff:<call_id>` có ràng buộc unique ở DB; trả `queued`, không bao giờ "connected".
  - `POST /internal/calls/{id}/end`: trạng thái cuối không lùi (AC05); `booked` tạo việc xác nhận lịch hẹn (`appointment:<call_id>`).
- Gateway (`gateway/backend.py`): hàng đợi trong bộ nhớ + task nền gửi theo lô, thử lại với backoff. Backend chết không làm hỏng cuộc gọi; khi kết thúc còn bản ghi chưa gửi thì báo trong summary/trang gọi thử. Riêng `request_handoff` chờ backend đồng bộ: thất bại thì tool trả `unavailable` để agent xin số và hẹn gọi lại.
- Mỗi lượt thoại lưu thời điểm người đó bắt đầu nói (VAD), không phải lúc transcript tới: OpenAI trả transcript khách sau khi agent đã trả lời. UI sắp xếp theo thời điểm này.
- Số điện thoại trong tham số tool được che, chỉ giữ 4 số cuối.
- Lưu là tùy chọn theo cuộc: trang gọi thử bật, eval/smoke tắt (eval có `--persist`).
- Mọi cột thời gian dùng kiểu `UTCDateTime`: SQLite trả giá trị không múi giờ, trình duyệt hiểu thành giờ địa phương (lệch 7 giờ).

## Hệ quả
- Hàng đợi chỉ nằm trong bộ nhớ: gateway chết giữa cuộc gọi sẽ mất phần chưa gửi. Khi có telephony thật (ADR 0004) cần cân nhắc ghi đệm ra đĩa hoặc Redis.
- Một service token dùng chung cho mọi tenant; khi có nhiều tenant/gateway thật cần token theo gateway và danh sách tenant được phép.
- Usage/chi phí chưa ghi vào backend (còn nằm trong báo cáo gateway).
