# ADR 0009 · Lịch làm việc, ngày nghỉ và định tuyến cuộc gọi đến theo giờ
Trạng thái: Đã chấp nhận · 20/10/2026

## Bối cảnh
M0 yêu cầu business calendar (giờ làm việc + ngày lễ). M1 mở đầu bằng định tuyến trong/ngoài giờ. Cuộc gọi ngoài giờ phải được AI tiếp nhận hoặc phát thông báo theo route; mọi yêu cầu chưa xong tạo đúng một task có owner mặc định, hạn trong khung làm việc kế tiếp (AC24). Ngày lễ và Tết phải dời lịch sang khung hợp lệ kế tiếp (AC23). Ngày lễ không có trong dữ liệu IANA, Tết theo âm lịch.

## Quyết định
- Bảng `business_calendars` (timezone IANA, `weekly_hours` theo thứ ISO 1–7, mỗi ngày nhiều khung giờ không chồng nhau, không qua nửa đêm; "24:00" là hết ngày), `calendar_exceptions` (holiday/closed đóng cả ngày, special_hours thay giờ thường; tối đa 31 ngày mỗi mục), `inbound_routes` (trong giờ / ngoài giờ: `agent` hoặc `announcement`; khi AI lỗi: `announcement`; người nhận việc ngoài giờ; nội dung thông báo).
- Thứ tự áp dụng trong một ngày: holiday/closed thắng; rồi special_hours mới nhất; rồi giờ trong tuần. Phép tính nằm trong `voiceos/domain/calendar.py` (hàm thuần, không DB), mọi phép so sánh theo múi giờ của lịch.
- Mỗi tenant có một lịch và route mặc định `number="*"`, tạo khi dùng lần đầu, kèm ngày nghỉ **mẫu** 2026–2027 có ghi chú "đối chiếu thông báo chính thức". Khi có SIP/đầu số (ADR 0004) route sẽ theo từng số.
- Backend quyết định `after_hours` của cuộc gọi từ lịch tại `started_at`, không tin giá trị gateway gửi.
- Gateway gọi `GET /internal/routing` khi cuộc gọi bắt đầu. Ngoài giờ + `agent`: thêm khối "Ngoài giờ làm việc" vào prompt (giờ mở cửa kế tiếp, không hứa chuyển máy, chỉ nói nhân viên gọi lại khi tool thành công). `announcement`: phiên chỉ đọc thông báo, không tool, vẫn có câu tự giới thiệu tự động và ghi âm. Backend không trả lời: trả lời như trong giờ, không bỏ rơi khách.
- Ngoài giờ, `request_handoff` tạo task `callback` (vẫn tối đa một task mỗi cuộc gọi) giao cho người nhận mặc định, hạn = giờ mở cửa kế tiếp + 30 phút, không quá cuối khung đó. Lịch hẹn đặt ngoài giờ tạo task xác nhận theo cùng quy tắc. Gỡ thành viên thì bỏ họ khỏi vai trò người nhận mặc định.
- API: `GET /business-calendars` (manager), `PUT /business-calendars/{id}` (admin, If-Match), `POST|DELETE /business-calendars/{id}/exceptions` (admin), `GET /inbound-routes` (manager), `PUT /inbound-routes/{id}` (admin, If-Match). Mọi thay đổi ghi audit.

## Hệ quả
- Ngày nghỉ mẫu có thể sai so với thông báo nghỉ lễ thật (ngày nghỉ bù, lịch Tết). Admin phải kiểm tra mỗi năm; màn Cài đặt hiện cảnh báo khi còn ngày mẫu.
- Chế độ "khi AI lỗi" mới chỉ lưu cấu hình; phát thông báo khi model không kết nối được cần telephony thật (ADR 0004).
- Chưa có lịch theo chi nhánh/tài nguyên (xe lái thử, khoang dịch vụ) và chưa áp dụng lịch cho automation gọi ra (M2, AC23 bước recheck).
- Thông báo ngoài giờ vẫn đọc bằng model realtime nên có tốn phí; khi có tổng đài thật có thể phát file âm thanh thu sẵn.
