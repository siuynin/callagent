# ADR 0005 · OpenAI Realtime làm provider thứ hai
Trạng thái: Đã chấp nhận cho spike · 19/10/2026

## Bối cảnh
Chủ sản phẩm yêu cầu thêm OpenAI Realtime (WebSocket, LLM + giọng nói realtime) để so sánh với Gemini Live trên cùng bộ đo trước gate G-V. Kiến trúc đã có interface provider (ADR 0003) nên chỉ cần thêm adapter.

## Thông tin đã xác minh (19/10/2026)
Nguồn: https://developers.openai.com/api/docs/guides/realtime-websocket, `/realtime-conversations`, `/realtime-function-calling`, và kiểu dữ liệu trong SDK Python `openai` 2.54.0 (`openai.types.realtime`).
- Endpoint `wss://api.openai.com/v1/realtime?model=...`, xác thực `Authorization: Bearer` phía server. Model trong ví dụ chính thức: `gpt-realtime-2.1` (cấu hình qua `OPENAI_REALTIME_MODEL`).
- `session.update` với `session.type = "realtime"`, `audio.input.format`, `audio.input.transcription` (`model`, `language`), `audio.input.turn_detection` (`server_vad` có `silence_duration_ms`, `prefix_padding_ms`, `create_response`, `interrupt_response`; hoặc `semantic_vad` có `eagerness`), `audio.output.format`, `audio.output.voice`, `tools`, `tool_choice`.
- Định dạng âm thanh theo SDK: `audio/pcm` chỉ 24 kHz; `audio/pcmu`, `audio/pcma` (G.711 8 kHz). Giọng có sẵn: alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar (khuyến nghị marin/cedar). Không đổi giọng sau khi model đã phát âm thanh.
- Sự kiện server: `response.output_audio.delta`, `response.output_audio_transcript.delta`, `conversation.item.input_audio_transcription.completed`, `input_audio_buffer.speech_started/stopped`, `response.function_call_arguments.done`, `response.done` (có `usage` theo từng response), `error`.
- Qua WebSocket, khi khách chen ngang client phải gửi `conversation.item.truncate` (`item_id`, `content_index`, `audio_end_ms` = phần khách đã nghe). WebRTC/SIP tự cắt.
- Kết quả tool: `conversation.item.create` với `function_call_output` rồi `response.create`.
- Phiên tối đa 60 phút.
Giá chưa xác minh trong ADR này; báo cáo chỉ tính chi phí khi điền `OPENAI_PRICE_*` từ trang giá chính thức.

## Quyết định
- Adapter `media-gateway/gateway/providers/openai_realtime.py` dùng SDK chính thức, ánh xạ về cùng bộ sự kiện với Gemini.
- Âm thanh khách 16 kHz được resample lên 24 kHz; đầu ra 24 kHz như Gemini.
- Cắt lời: gateway ước lượng phần khách đã nghe bằng thời gian từ chunk âm thanh đầu tiên của item, chặn trên bởi tổng âm thanh đã gửi. Khi có telephony thật sẽ dùng mốc phát thực tế của leg thoại.
- Kết quả tool được giữ lại đến khi `response.done` và mọi function call của response đã có kết quả, rồi mới `response.create` một lần.
- `usage` của OpenAI được cộng dồn theo response (mỗi response tính lại toàn bộ ngữ cảnh). Usage của Gemini chưa rõ là cộng dồn hay theo lượt nên giữ snapshot lớn nhất và ghi chú cần đối chiếu billing.
- Cả hai provider chủ động chào khách khi bắt đầu cuộc gọi (inbound receptionist), Gemini chỉ chào ở lần kết nối đầu, không chào lại khi resume.
- Trang gọi thử và eval runner chọn provider theo từng cuộc (`?provider=`, `--provider`), chỉ hiện provider đã có key. Giá cấu hình riêng theo provider (`GEMINI_PRICE_*`, `OPENAI_PRICE_*`).

## Hệ quả
- So sánh A/B công bằng trên cùng prompt, tool, VAD và bộ đo.
- Với telephony sau này, OpenAI nhận G.711 trực tiếp nên có thể bỏ bước resample; cần đo lại khi có SIP trunk (ADR 0004).
- Chưa dùng tính năng tiết kiệm chi phí (cache, giới hạn ngữ cảnh `truncation`); đánh giá sau khi có số đo thật.

## Kết quả đo đầu tiên (19/10/2026, gpt-realtime-2.1, giọng khách TTS tổng hợp, chưa qua đường điện thoại)
Tài khoản có các model realtime: `gpt-realtime-2.1` (mới nhất của dòng Realtime, 23/06/2026), `gpt-realtime-2.1-mini`, và `gpt-live-1` (08/09/2026, API GPT-Live khác hẳn, chưa có adapter). Nhận dạng giọng nói chuyển sang `gpt-transcribe` (07/2026) thay cho `gpt-4o-transcribe`.

| Chỉ số | Đặt lịch lái thử (5 lượt, 104 s) | Hỏi trả góp (2 lượt, 43 s) |
|---|---|---|
| Mở phiên (kết nối + session.update) | 2,3–3,3 s | |
| Âm thanh chào đầu tiên sau khi mở phiên | ~1,1 s | |
| Độ trễ lượt p50 / p95 / max | 606 / 1.223 / 1.396 ms | 831 / 897 / 905 ms |
| Tool đúng | tra lịch → tạo lịch với đúng tên, số, giờ | chuyển nhân viên, không tạo lịch |
| Xác nhận sai | 0 | 0 |
| Token vào / ra | 18.083 (94% text) / 2.103, 10 response | 6.058 / 724, 4 response |

Những gì vòng đo bắt được và đã sửa:
- Prompt cũ khiến agent bắt khách chọn lại giờ đã nói, lặp câu hỏi, không đọc lại số → sửa quy trình đặt lịch (nhận thông tin theo mọi thứ tự, chốt giờ khách nêu nếu còn trống, đọc lại một lần).
- Agent nói "em đã giữ 15 giờ" sau khi chỉ tra lịch → bộ đo AC21 bắt được; prompt cấm "giữ chỗ" trước khi tạo lịch.
- TTS đôi khi đọc lặp câu → công cụ tạo giọng mẫu tự chuyển ngược thành chữ và tạo lại khi lệch.

Nhận xét:
- Mỗi response tính lại toàn bộ ngữ cảnh; phần lớn là text (prompt + tool). Báo cáo đã ghi `CACHED` để ước tính giá cache; cần rút gọn prompt/tool và đo với cuộc gọi dài.
- Giọng TTS sạch hơn khách thật; số đo này kiểm tra logic, chưa thay được bản ghi giọng thật các vùng miền cho gate G-V.
