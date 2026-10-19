"""Synthesize caller turns for eval scenarios with OpenAI TTS (synthetic voices, no real person).

  python -m gateway.tts_fixtures "../eval/scenarios/tts-*.json" [--force]

For every turn that has "text" and whose "audio" file is missing, generates a WAV. Synthetic speech is
cleaner than a real phone caller: it checks the pipeline and agent logic, it does NOT replace recordings
of real Vietnamese accents for gate G-V (eval/README.md).
"""

import argparse
import asyncio
import difflib
import glob
import json
import re
import wave
from pathlib import Path

from openai import AsyncOpenAI

from gateway.config import get_settings

TTS_MODEL = "gpt-4o-mini-tts-2025-12-15"
MAX_TRIES = 3
MIN_SIMILARITY = 0.8
DEFAULT_STYLE = (
    "Nói tiếng Việt tự nhiên như một khách hàng đang gọi điện thoại cho showroom ô tô, "
    "tốc độ bình thường, không đọc như phát thanh viên."
)


def fix_wav_header(path: Path) -> None:
    """Streamed WAV responses carry a placeholder frame count; rewrite a standard header."""
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        frames = w.readframes(w.getnframes())
    with wave.open(str(path), "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(frames)


async def synthesize(client: AsyncOpenAI, text: str, voice: str, style: str, out: Path) -> None:
    async with client.audio.speech.with_streaming_response.create(
        model=TTS_MODEL, voice=voice, input=text, instructions=style, response_format="wav"
    ) as resp:
        out.parent.mkdir(parents=True, exist_ok=True)
        await resp.stream_to_file(out)
    fix_wav_header(out)


def _norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def similarity(expected: str, heard: str) -> float:
    """TTS models occasionally repeat or drop words; a repeated sentence halves this ratio."""
    return difflib.SequenceMatcher(None, _norm(expected), _norm(heard)).ratio()


async def transcribe(client: AsyncOpenAI, path: Path, model: str) -> str:
    with path.open("rb") as f:
        result = await client.audio.transcriptions.create(model=model, file=f, language="vi")
    return result.text


async def make_verified(
    client, text: str, voice: str, style: str, out: Path, stt_model: str
) -> tuple[float, str]:
    best = (0.0, "")
    for _ in range(MAX_TRIES):
        await synthesize(client, text, voice, style, out)
        heard = await transcribe(client, out, stt_model)
        score = similarity(text, heard)
        best = max(best, (score, heard))
        if score >= MIN_SIMILARITY:
            return score, heard
    return best


async def main_async(patterns: list[str], force: bool, verify_only: bool = False) -> int:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    paths = sorted({Path(p) for pattern in patterns for p in glob.glob(pattern)})
    made, bad = 0, 0
    for path in paths:
        scenario = json.loads(path.read_text(encoding="utf-8"))
        voice = scenario.get("tts_voice", "ash")
        style = scenario.get("tts_style", DEFAULT_STYLE)
        for turn in scenario["turns"]:
            out = (path.parent / turn["audio"]).resolve()
            if verify_only:
                if not out.exists():
                    continue
                heard = await transcribe(client, out, settings.openai_transcribe_model)
                score = similarity(turn["text"], heard)
            elif out.exists() and not force:
                continue
            else:
                score, heard = await make_verified(
                    client, turn["text"], voice, style, out, settings.openai_transcribe_model
                )
                made += 1
            ok = score >= MIN_SIMILARITY
            bad += not ok
            print(f"  {'✓' if ok else '✗'} {out.name} ({score:.2f})  ←  {turn['text']}")
            if not ok:
                print(f"      nghe được: {heard}")
    print(f"Đã tạo {made} file · {bad} file không khớp văn bản")
    return 1 if bad else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic caller audio for eval scenarios")
    ap.add_argument("scenarios", nargs="+")
    ap.add_argument("--force", action="store_true", help="regenerate existing files")
    ap.add_argument("--verify", action="store_true", help="only transcribe existing files and compare")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main_async(args.scenarios, args.force, args.verify)))


if __name__ == "__main__":
    main()
