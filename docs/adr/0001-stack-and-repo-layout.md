# ADR 0001 · Stack và bố cục repo
Trạng thái: Đã chấp nhận · 17/10/2026

## Bối cảnh
Gói đặc tả `../plan` (v1.1) đề xuất Next.js + FastAPI + PostgreSQL/pgvector + Redis + media gateway riêng. Chủ sản phẩm xác nhận giữ stack này và tạo repo mới cạnh `plan/`.

## Quyết định
- Monorepo `voiceos/`:
  - `web/`: Next.js + TypeScript (App Router), giao diện tiếng Việt. Port dần các màn từ `plan/template` thành component, không copy JS nguyên khối.
  - `backend/`: package Python `voiceos` chứa **api** (FastAPI) và **worker** (process riêng, cùng codebase), SQLAlchemy 2 + Alembic.
  - `media-gateway/`: service Python riêng cho phiên thoại dài, cô lập với job nền. Không import code của backend; giao tiếp qua API/sự kiện.
  - `eval/`: kịch bản bộ đánh giá voice (docs/02 của plan).
  - `docs/adr/`: quyết định kiến trúc.
- Python 3.12+ (dev dùng 3.13), Node 22.
- Đặc tả nguồn vẫn ở `../plan`; khi đặc tả đổi, cập nhật plan trước rồi mới đổi code.

## Hệ quả
- Ba đơn vị build độc lập, CI chạy riêng từng phần.
- Thư viện dùng chung giữa backend và gateway (nếu cần) sẽ tách thành package riêng sau, không chia sẻ bằng import đường dẫn.
