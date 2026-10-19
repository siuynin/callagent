# ADR 0004 · Telephony
Trạng thái: Đề xuất, chờ kết quả voice spike và SIP trunk test · 17/10/2026

## Lựa chọn
- A: Asterisk/PJSIP + ARI external media tự vận hành.
- B: SIP trunk của nhà mạng/CPaaS có cầu nối media WebSocket.

## Tiêu chí quyết định
Chuyển máy có xác nhận, ghi âm, DTMF, giới hạn kênh, chi phí/phút, đầu số Việt Nam, độ trễ đến region của model, khối lượng vận hành.

## Việc đã chuẩn bị
`media-gateway/gateway/audio.py` có G.711 (μ-law/A-law) và resample 8k/16k/24k để dùng cho cả hai phương án.
