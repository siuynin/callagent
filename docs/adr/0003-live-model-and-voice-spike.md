# ADR 0003 · Live model và voice spike (M0.5)
Trạng thái: Đã chấp nhận cho spike · 17/10/2026

## Thông tin đã xác minh từ tài liệu chính thức (17/10/2026)
Nguồn: https://ai.google.dev/gemini-api/docs/live-api, `/live-api/get-started-sdk`, `/live-api/capabilities`, `/live-api/tools`, `/live-api/session-management`.
- Model trong ví dụ SDK: `gemini-3.8-live` (cấu hình qua `AI_MODEL`, không hardcode).
- SDK Python `google-genai`: `client.aio.live.connect(model, config)`, `session.send_realtime_input(audio=types.Blob(data, mime_type="audio/pcm;rate=16000"))`, `session.receive()`, `session.send_tool_response(function_responses=[types.FunctionResponse(id, name, response)])`.
- Âm thanh: vào PCM16 little-endian 16 kHz; ra PCM16 24 kHz.
- `server_content.interrupted` = VAD hủy generation → client phải dừng phát và xóa hàng đợi; function call đang chờ bị hủy.
- VAD: `realtime_input_config.automatic_activity_detection` (`start_of_speech_sensitivity`, `end_of_speech_sensitivity`, `prefix_padding_ms`, `silence_duration_ms`; khuyến nghị 500–800 ms).
- Transcription: `input_audio_transcription`, `output_audio_transcription`.
- Ngôn ngữ: native audio tự chọn ngôn ngữ, không có language code; tiếng Việt (`vi`) có trong bảng hỗ trợ; ràng buộc bằng system instruction.
- Giới hạn: phiên audio ~15 phút nếu không nén context; kết nối ~10 phút; có `context_window_compression` (sliding window), `session_resumption` (handle hết hạn 2 giờ), thông điệp `go_away` với `time_left`.
- Tool mặc định blocking; `NON_BLOCKING` không áp dụng cho mọi model.
- Usage: `usage_metadata.total_token_count`, `response_tokens_details` theo modality.
Giá chưa xác minh trong ADR này; báo cáo spike chỉ tính chi phí khi `PRICE_*` được điền từ trang giá chính thức.

## Quyết định
- Media gateway có interface provider (`mock`, `gemini`); mặc định `mock`.
- Spike giai đoạn 1 không cần SIP: trình duyệt (mic) → gateway WebSocket → Gemini Live. Có chế độ **mô phỏng điện thoại**: hạ 16 kHz → 8 kHz → G.711 → giải mã → 16 kHz trước khi gửi model, để đo chất lượng nhận dạng ở băng thông thoại.
- Gateway bật transcription hai chiều, context window compression, session resumption; tự nối lại khi `go_away`.
- VAD do model quyết định (một nguồn duy nhất). Gateway chỉ có VAD năng lượng để **đo** độ trễ, không điều khiển lượt.
- Mỗi phiên ghi báo cáo JSONL: độ trễ theo lượt, sự kiện ngắt lời, tool call, token usage, cờ xác nhận sai (AI nói "đã đặt" khi chưa có tool create_appointment thành công).
- Giai đoạn 2 (khi có SIP trunk test): nối telephony theo ADR 0004.

## Hệ quả
Số đo từ trình duyệt chưa gồm độ trễ mạng PSTN; báo cáo G-V phải tách hai loại số đo.
