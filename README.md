# VoiceOS

Nền tảng tổng đài AI tiếng Việt. Đặc tả nguồn: [`../plan`](../plan/README.md) (v1.1). Quyết định kiến trúc: [`docs/adr`](docs/adr) (Gemini Live: ADR 0003, OpenAI Realtime: ADR 0005, gateway ghi vào backend: ADR 0006).

## Trạng thái (19/10/2026)

| Phần | Trạng thái |
|---|---|
| M0 nền tảng | Đang làm. Đã có repo, ADR 0001–0004, models + migration đầu, tenant scoping, RBAC, idempotency, If-Match, outbox worker, CI |
| M0.5 voice spike | Code xong, **chưa đo với model thật**. Gateway, adapter Gemini Live và OpenAI Realtime (so sánh A/B), mock, trang gọi thử, mô phỏng đường điện thoại 8 kHz, bộ đo, eval runner |
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

Lưu cuộc gọi vào VoiceOS (ADR 0006): đặt cùng một `GATEWAY_SERVICE_TOKEN` cho backend và gateway trong `.env`, cùng `GATEWAY_TENANT_ID` (tenant dev: `00000000-0000-4000-8000-00000000000a`) và `BACKEND_URL`. Khởi động lại cả hai. Khi đó mỗi cuộc gọi thử hiện ở màn Cuộc gọi kèm transcript và tool; khách đòi gặp nhân viên tạo việc trong Hộp việc; cuộc đặt lịch tạo việc xác nhận lịch hẹn. Eval chỉ lưu khi thêm `--persist`.

Dữ liệu mẫu cho giao diện (chỉ dev): `.venv/Scripts/python -m voiceos.seed_demo` trong `backend/`.

Web:

```bash
cd web && npm install && npm run dev
```

Mở http://localhost:3000.

## Đo voice spike với model thật (Gemini và OpenAI)

1. Trong `voiceos/.env` điền key của provider muốn đo: `GEMINI_API_KEY=...` và/hoặc `OPENAI_API_KEY=...`. **Không dán key vào chat, issue hay commit.**
   - Gemini: model mặc định `gemini-3.8-live` (ADR 0003), đổi bằng `AI_MODEL`.
   - OpenAI: model mặc định `gpt-realtime-2.1`, giọng `marin` (ADR 0005); đổi bằng `OPENAI_REALTIME_MODEL`, `OPENAI_VOICE`, `OPENAI_VAD`.
2. Kiểm tra nhanh không cần micro (mở phiên thật, chờ AI chào, đo thời gian tới âm thanh đầu tiên, tốn vài giây usage):
   ```bash
   cd media-gateway
   .venv/Scripts/python -m gateway.smoke --provider openai
   .venv/Scripts/python -m gateway.smoke --provider gemini
   ```
   `"ok": true` nghĩa là key, tên model và cấu hình session được API chấp nhận.
3. Khởi động lại gateway. Ô "Nhà cung cấp" trên trang gọi thử chỉ liệt kê provider đã có key.
4. Gọi cùng một kịch bản với từng provider: đặt lịch lái thử, đọc số điện thoại, hỏi trả góp (phải chuyển nhân viên), chen ngang khi AI đang nói. Lặp lại khi bật "Mô phỏng đường điện thoại 8 kHz".
5. Mỗi cuộc ghi một báo cáo JSON ở `media-gateway/reports/` có `provider`, `model`, độ trễ p50/p95, ngắt lời, tool, số lần xác nhận sai, token.
6. Số đo lặp lại được: ghi âm kịch bản theo [`eval/README.md`](eval/README.md), rồi chạy cùng bộ kịch bản cho từng provider:
   `python -m gateway.eval_runner "../eval/scenarios/*.json" --provider gemini` và `--provider openai`.
7. Chi phí/phút chỉ được tính khi điền `GEMINI_PRICE_*` / `OPENAI_PRICE_*` từ trang giá chính thức. Usage của OpenAI được cộng dồn theo từng response (mỗi lượt tính lại ngữ cảnh), chưa trừ giảm giá cache; luôn đối chiếu với billing.

Nếu `.env` của bạn tạo từ bản trước còn các dòng `PRICE_*` không tiền tố provider, các dòng đó không còn được đọc; dùng tên mới ở `.env.example`.

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
- Inbox, handoff, lịch hẹn thật, thông báo nhân viên — M1.
