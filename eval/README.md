# Bộ đánh giá voice tiếng Việt (gate G-V)
Mục tiêu: đo trên dữ liệu lặp lại được thay vì cảm nhận khi gọi thử. Chạy lại trên mỗi thay đổi prompt, model hoặc đường audio.

## Ghi âm kịch bản
- Mỗi lượt khách là một file WAV mono PCM 16-bit (16 kHz hoặc 48 kHz đều được, runner tự resample) trong `audio/`.
- Ghi bằng điện thoại hoặc micro thường, không cần phòng thu. Nên có nhiều giọng: Bắc, Trung, Nam, Tây Nguyên; nam/nữ; có tiếng ồn đường phố.
- Mỗi file chỉ chứa câu nói của khách, im lặng ngắn ở đầu/cuối. Runner tự chèn im lặng chờ AI trả lời.
- File audio chứa giọng người thật: chỉ dùng khi người nói đồng ý, không commit (`audio/*.wav` đã gitignore).

## Giọng tổng hợp (TTS) để thử nhanh
Kịch bản `scenarios/tts-*.json` có `"synthetic": true`: giọng khách được tạo bằng OpenAI TTS, không phải người thật. Dùng để kiểm tra logic agent và đường âm thanh, **không thay** bản ghi giọng thật các vùng miền cho gate G-V.
```bash
cd ../media-gateway
.venv/Scripts/python -m gateway.tts_fixtures "../eval/scenarios/tts-*.json"            # tạo file còn thiếu
.venv/Scripts/python -m gateway.tts_fixtures "../eval/scenarios/tts-*.json" --verify   # kiểm tra lại file đã có
```
Mỗi file được chuyển ngược thành chữ và so với câu gốc; TTS thỉnh thoảng đọc lặp câu, khi đó công cụ tự tạo lại (tối đa 3 lần) và báo ✗ nếu vẫn lệch.

## Định dạng scenario (`scenarios/*.json`)
```json
{
  "id": "dat-lich-lai-thu-giong-bac",
  "description": "Khách đặt lái thử, đọc số điện thoại theo nhóm",
  "phone_sim": "alaw",
  "turns": [
    {"audio": "../audio/dat-lich-1.wav", "text": "Chào em, anh muốn lái thử SUV chiều mai"},
    {"audio": "../audio/dat-lich-2.wav", "text": "Ba giờ chiều nhé"}
  ],
  "expect": {
    "tools": [{"name": "create_appointment", "args_subset": {"phone": "0901234567"}}],
    "tools_absent": [],
    "no_false_confirm": true,
    "max_p95_latency_ms": 2000,
    "agent_says_any": ["ghi âm"]
  }
}
```
- `phone_sim`: `alaw`/`ulaw` để mô phỏng đường điện thoại 8 kHz; bỏ trống để dùng audio gốc.
- `text` chỉ để người đọc hiểu kịch bản, runner không dùng.
- `args_subset` so khớp sau khi bỏ dấu cách/ký tự đặc biệt và viết thường.

## Chạy
```bash
cd ../media-gateway
.venv/Scripts/python -m gateway.eval_runner "../eval/scenarios/*.json" --provider gemini
.venv/Scripts/python -m gateway.eval_runner "../eval/scenarios/*.json" --provider openai
```
Chạy cùng bộ kịch bản cho từng provider để so sánh. Kết quả: `results/eval-<thời gian>.json` (gitignore vì chứa transcript) gồm từng check, độ trễ p50/p95, số lần xác nhận sai, token.

## Ngưỡng G-V đề xuất (chủ sản phẩm duyệt lại)
| Chỉ số | Ngưỡng |
|---|---|
| Xác nhận sai (AC21) | 0 trên toàn bộ kịch bản |
| Số điện thoại đúng trong create_appointment | ≥ 95% kịch bản |
| Ngày giờ đúng | ≥ 95% |
| Độ trễ p95 (trình duyệt) | ≤ 2.000 ms |
| Dừng nói khi bị chen ngang p95 | ≤ 500 ms |
| Số kịch bản | ≥ 50, mỗi vùng giọng ≥ 10 |
