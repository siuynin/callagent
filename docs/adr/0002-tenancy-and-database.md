# ADR 0002 · Tenancy và cơ sở dữ liệu
Trạng thái: Đã chấp nhận · 17/10/2026

## Quyết định
- PostgreSQL là system of record. Mọi bảng nghiệp vụ có `tenant_id`, `created_at`, `updated_at`; bảng thay đổi được có `version` cho optimistic locking.
- M0 dùng **tenant scoping bắt buộc ở tầng ứng dụng**: mọi truy vấn đi qua repository nhận `TenantContext`; tenant lấy từ membership đã xác thực, không lấy từ body. Test AC01 bắt buộc. RLS Postgres bổ sung ở M5 như lớp phòng thủ thứ hai.
- Kiểu dữ liệu portable của SQLAlchemy (`Uuid`, `DateTime(timezone=True)`, `JSON`) để test nhanh trên SQLite cục bộ; CI chạy cùng bộ test trên Postgres 17 + pgvector. Ràng buộc chỉ có trên Postgres (exclusion constraint lịch hẹn, RLS, pgvector) có test đánh dấu `postgres_only`.
- Tiền tệ lưu số nguyên minor units + mã tiền tệ.
- Thời gian lưu UTC; hiển thị/đánh giá lịch theo IANA của tenant (mặc định Asia/Ho_Chi_Minh).

## Lý do
Máy dev hiện chưa có Docker/Postgres; không muốn chặn M0. Rủi ro lệch hành vi SQLite/Postgres được kiểm soát bằng CI Postgres.
