import numpy as np
import pytest
from conftest import tone

from gateway import audio


def _snr(a: bytes, b: bytes, trim: int = 200) -> float:
    x, y = audio.pcm16_to_float(a)[trim:-trim], audio.pcm16_to_float(b)[trim:-trim]
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    return 10 * np.log10(np.sum(x**2) / np.sum((x - y) ** 2))


@pytest.mark.parametrize("codec", ["ulaw", "alaw"])
def test_g711_roundtrip_quality(codec):
    pcm = tone(1000, 440, 0.5)
    enc, dec = getattr(audio, f"{codec}_encode"), getattr(audio, f"{codec}_decode")
    coded = enc(pcm)
    assert len(coded) == len(pcm) // 2  # 8 bits per sample
    assert _snr(pcm, dec(coded)) > 33  # G.711 gives ~38 dB on a sine


def test_g711_extremes_do_not_overflow():
    pcm = np.array([-32768, -1, 0, 1, 32767], dtype="<i2").tobytes()
    for codec in ("ulaw", "alaw"):
        out = np.frombuffer(getattr(audio, f"{codec}_decode")(getattr(audio, f"{codec}_encode")(pcm)), "<i2")
        assert out[0] < -30000 and out[-1] > 30000


def test_resample_lengths():
    pcm = tone(1000)
    assert len(audio.resample(pcm, 16000, 8000)) == 8000 * 2
    assert len(audio.resample(pcm, 16000, 24000)) == 24000 * 2
    assert audio.resample(pcm, 16000, 16000) is pcm


def test_downsample_removes_content_above_new_nyquist():
    hi = tone(1000, 6000, 0.5)  # above 4 kHz Nyquist of 8 kHz
    narrow = audio.resample(hi, 16000, 8000)
    assert audio.rms_dbfs(narrow) < audio.rms_dbfs(hi) - 20


def test_phone_sim_keeps_speech_band():
    pcm = tone(1000, 1000, 0.5)
    assert _snr(pcm, audio.phone_channel_sim(pcm)) > 25
