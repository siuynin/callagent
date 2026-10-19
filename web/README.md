# VoiceOS web

Next.js 16 (App Router, `cacheComponents`). Xem README ở thư mục gốc để chạy cả hệ thống.

- Dữ liệu động đặt trong `<Suspense>` và gọi `connection()` trước khi fetch (yêu cầu của cacheComponents).
- Gọi API ở server (`src/lib/api.ts`, `server-only`); token dev không xuống trình duyệt. Trình duyệt gọi `/api/v1/*` cùng origin qua rewrite.
- Giao diện tiếng Việt; mobile hiển thị danh sách dạng thẻ cho nhân viên.
- Trước khi viết code mới, đọc tài liệu trong `node_modules/next/dist/docs/` (xem `AGENTS.md`).
