import math
import wave
from pathlib import Path

import numpy as np
import pytest

from gateway.audio import float_to_pcm16
from gateway.config import Settings

RATE = 16000
CHUNK = 640  # 40 ms


def tone(ms: int, freq: float = 220.0, amp: float = 0.3) -> bytes:
    t = np.arange(int(RATE * ms / 1000)) / RATE
    return float_to_pcm16((amp * np.sin(2 * math.pi * freq * t)).astype(np.float32))


def silence(ms: int) -> bytes:
    return b"\x00" * (int(RATE * ms / 1000) * 2)


def chunks(data: bytes, size: int = CHUNK * 2):
    return [data[i : i + size] for i in range(0, len(data), size)]


def write_wav(path: Path, pcm: bytes, rate: int = RATE) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(_env_file=None, ai_provider="mock", reports_dir=tmp_path / "reports", gemini_api_key="")
