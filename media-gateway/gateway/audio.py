"""PCM16 helpers, G.711 codecs and resampling (plan/docs/02 "Đường audio").

All PCM is mono, signed 16-bit little-endian. `audioop` is gone in Python 3.13, so G.711 is
implemented with numpy following ITU-T G.711 (same segment tables as the classic Sun reference).
"""

from functools import lru_cache

import numpy as np

# --- PCM16 <-> float ---


def pcm16_to_float(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def float_to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0 - 1 / 32768) * 32768.0).astype("<i2").tobytes()


def rms_dbfs(data: bytes) -> float:
    x = pcm16_to_float(data)
    if x.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(x * x)))
    return 20 * np.log10(max(rms, 1e-6))


def duration_ms(data: bytes, rate: int) -> float:
    return len(data) / 2 / rate * 1000


# --- resampling: windowed-sinc low-pass + linear interpolation ---


@lru_cache(maxsize=16)
def _lowpass(cutoff: float, taps: int = 63) -> np.ndarray:
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff * n) * np.hamming(taps)
    return (h / h.sum()).astype(np.float32)


def resample(data: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate or not data:
        return data
    x = pcm16_to_float(data)
    if dst_rate < src_rate:  # anti-alias before decimation
        x = np.convolve(x, _lowpass(0.5 * dst_rate / src_rate * 0.95), mode="same")
    n_out = int(round(x.size * dst_rate / src_rate))
    t_out = np.arange(n_out) * (src_rate / dst_rate)
    y = np.interp(t_out, np.arange(x.size), x).astype(np.float32)
    return float_to_pcm16(y)


# --- G.711 ---

_BIAS = 0x84
_CLIP = 32635


def ulaw_encode(data: bytes) -> bytes:
    s = np.frombuffer(data, dtype="<i2").astype(np.int32)
    sign = np.where(s < 0, 0x80, 0)
    mag = np.minimum(np.abs(s), _CLIP) + _BIAS
    v = mag >> 7  # 1..255 after bias
    exp = np.floor(np.log2(np.maximum(v, 1))).astype(np.int32)
    mant = (mag >> (exp + 3)) & 0x0F
    return (~(sign | (exp << 4) | mant) & 0xFF).astype(np.uint8).tobytes()


def ulaw_decode(data: bytes) -> bytes:
    u = (~np.frombuffer(data, dtype=np.uint8)).astype(np.int32) & 0xFF
    sign = u & 0x80
    exp = (u >> 4) & 0x07
    mant = u & 0x0F
    mag = (((mant << 3) + _BIAS) << exp) - _BIAS
    return np.where(sign != 0, -mag, mag).astype("<i2").tobytes()


def alaw_encode(data: bytes) -> bytes:
    pcm = np.frombuffer(data, dtype="<i2").astype(np.int32) >> 3  # 13-bit
    positive = pcm >= 0
    mask = np.where(positive, 0xD5, 0x55)
    mag = np.where(positive, pcm, -pcm - 1)
    seg = np.zeros_like(mag)
    for i in range(1, 8):
        seg = np.where(mag >= (0x20 << (i - 1)), i, seg)
    mant = np.where(seg < 2, mag >> 1, mag >> seg) & 0x0F
    return (((seg << 4) | mant) ^ mask).astype(np.uint8).tobytes()


def alaw_decode(data: bytes) -> bytes:
    a = np.frombuffer(data, dtype=np.uint8).astype(np.int32) ^ 0x55
    sign = a & 0x80
    seg = (a >> 4) & 0x07
    mant = a & 0x0F
    mag = np.where(seg == 0, (mant << 4) + 8, ((mant << 4) + 0x108) << np.maximum(seg - 1, 0))
    return np.where(sign != 0, mag, -mag).astype("<i2").tobytes()


def phone_channel_sim(pcm16_16k: bytes, codec: str = "alaw") -> bytes:
    """Simulate a PSTN leg: 16 kHz -> 8 kHz -> G.711 -> 8 kHz -> 16 kHz (ADR 0003)."""
    narrow = resample(pcm16_16k, 16000, 8000)
    if codec == "ulaw":
        narrow = ulaw_decode(ulaw_encode(narrow))
    else:
        narrow = alaw_decode(alaw_encode(narrow))
    return resample(narrow, 8000, 16000)
