# VoiceOS

Nền tảng tổng đài AI tiếng Việt. Đặc tả nguồn: [`../plan`](../plan/README.md) (v1.1). Quyết định kiến trúc: [`docs/adr`](docs/adr).

## Trạng thái (19/10/2026)

| Phần | Trạng thái |
|---|---|
| M0 nền tảng | Đang làm. Đã có repo, ADR 0001–0004, models + migration đầu, tenant scoping, RBAC, idempotency, If-Match, outbox worker, CI |
| M0.5 voice spike | Code xong, **chưa đo với Gemini thật**. Gateway, adapter Gemini Live, mock, trang gọi thử, mô phỏng đường điện thoại 8 kHz, bộ đo, eval runner |
| Web | Khung Next.js: Tổng quan, Khách hàng (đọc API thật), trang voice spike |
| Xác thực | Chỉ có token dev (`APP_ENV=dev`). OIDC ở M1 |
| Postgres | CI chạy Postgres 17 + pgvector; máy dev đang dùng SQLite (ADR 0002) |

Mặc định an toàn: `CALL_PROVIDER=mock`, `CONNECTOR_MODE=mock`, `NOTIFY_PROVIDER=mock`, `OUTBOUND_ENABLED=false`, `AI_PROVIDER=mock`.

## Cấu trúc

```
backend/        FastAPI api + worker (package voiceos), Alembic migrations
media-gateway/  phiên thoại realtime, adapter Gemini Live, voice spike, eval runner
web/            Next.js 16 (App Router, cacheComponents)
eval/           kịch bản đánh giá voice (gate G-V)
docs/adr/       quyết định kiến trúc
```

## Chạy trên máy dev (Windows, Git Bash)

Cần Python 3.12+ và Node 22. Docker không bắt buộc (dùng nếu muốn Postgres/Redis local: `docker compose up -d`).

```bash
cp .env.example .env            # rồi điền GEMINI_API_KEY nếu đo với model thật
cp web/.env.example web/.env.local
```

Backend:

```bash
cd backend
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m voiceos.seed       # in ra token dev của 2 tenant mẫu
.venv/Scripts/python -m uvicorn voiceos.api.main:app --port 8000
.venv/Scripts/python -m voiceos.worker     # cửa sổ khác: outbox worker
```

API docs: http://127.0.0.1:8000/api/v1/docs

Media gateway (voice spike):

```bash
cd media-gateway
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m uvicorn gateway.main:app --host 127.0.0.1 --port 8100
```

Mở http://127.0.0.1:8100, bấm "Bắt đầu cuộc gọi" và nói vào micro. Gateway chỉ nghe trên 127.0.0.1 để API key không ra ngoài máy.

Web:

```bash
cd web && npm install && npm run dev
```

Mở http://localhost:3000.

## Đo voice spike với Gemini thật

1. Trong `.env`: `AI_PROVIDER=gemini`, `GEMINI_API_KEY=...`. Model mặc định `gemini-3.8-live` theo tài liệu chính thức ngày 17/10/2026 (ADR 0003); đổi bằng `AI_MODEL` nếu tài khoản dùng tên khác.
2. Khởi động lại gateway. Góc phải trang gọi thử phải hiện "Gemini Live · …".
3. Gọi thử vài kịch bản: đặt lịch lái thử, đọc số điện thoại, hỏi trả góp (phải chuyển nhân viên), chen ngang khi AI đang nói. Lặp lại với ô "Mô phỏng đường điện thoại 8 kHz".
4. Mỗi cuộc ghi một báo cáo JSON ở `media-gateway/reports/` (độ trễ p50/p95, ngắt lời, tool, số lần xác nhận sai, token).
5. Muốn số đo lặp lại được: ghi âm kịch bản theo [`eval/README.md`](eval/README.md) rồi chạy `python -m gateway.eval_runner "../eval/scenarios/*.json" --provider gemini`.
6. Chi phí/phút chỉ được tính khi điền `PRICE_*` từ trang giá chính thức; báo cáo ghi rõ cần đối chiếu với billing.

Báo cáo và file ghi âm chứa transcript/giọng nói nên không được commit (đã gitignore).

## Kiểm thử

```bash
cd backend && .venv/Scripts/python -m pytest -q
cd media-gateway && .venv/Scripts/python -m pytest -q
cd web && npm run lint && npm run build
```

CI chạy backend trên Postgres, gateway với mock provider (không bao giờ gọi model thật), và build web.

## Chưa làm (theo plan/docs/07)

- OIDC, phân quyền theo chi nhánh, RLS Postgres.
- Telephony thật (ADR 0004 chờ SIP trunk test và kết quả spike).
- Lưu cuộc gọi từ gateway vào backend (call/turn/tool_run) — M1.
- Inbox, handoff, lịch hẹn thật, thông báo nhân viên — M1.
