"""Deterministic offline provider for tests and UI work. Clearly labelled; never falls back to live.

Behaviour: uses an energy VAD on incoming audio; after ~600 ms of silence following speech it
"answers". Every second customer turn it first calls `check_available_slots`, waits for the tool
result, then speaks. Speech is a 24 kHz tone so playback, pacing and barge-in can be exercised.
"""

import asyncio
import math
from collections.abc import AsyncIterator
from datetime import date, timedelta

import numpy as np

from gateway.audio import float_to_pcm16, rms_dbfs
from gateway.providers.base import (
    AudioOut,
    Event,
    InputTranscript,
    Interrupted,
    OutputTranscript,
    SessionSpec,
    SpeechEnded,
    SpeechStarted,
    ToolCall,
    ToolResult,
    TurnComplete,
    Usage,
)

SPEECH_DBFS = -45.0
SILENCE_MS = 600
OUT_RATE = 24000
CHUNK_MS = 40


def _tone(ms: int, freq: float = 330.0) -> bytes:
    t = np.arange(int(OUT_RATE * ms / 1000)) / OUT_RATE
    env = np.minimum(1, np.minimum(t, t[::-1]) * 50)  # short fade in/out
    return float_to_pcm16((0.2 * np.sin(2 * math.pi * freq * t) * env).astype(np.float32))


class MockLiveSession:
    output_rate = OUT_RATE

    def __init__(self, spec: SessionSpec):
        self.spec = spec
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()
        self._speaking = False
        self._silence_ms = 0.0
        self._turns = 0
        self._reply_task: asyncio.Task | None = None
        self._tool_wait: asyncio.Future | None = None
        self._closed = False

    async def send_audio(self, pcm16_16k: bytes) -> None:
        ms = len(pcm16_16k) / 2 / 16000 * 1000
        loud = rms_dbfs(pcm16_16k) > SPEECH_DBFS
        if loud:
            if not self._speaking:
                self._speaking = True
                await self._queue.put(SpeechStarted())
                if self._reply_task and not self._reply_task.done():
                    self._reply_task.cancel()  # barge-in
                    await self._queue.put(Interrupted())
            self._silence_ms = 0
        elif self._speaking:
            self._silence_ms += ms
            if self._silence_ms >= SILENCE_MS:
                self._speaking = False
                self._turns += 1
                await self._queue.put(SpeechEnded())
                await self._queue.put(InputTranscript(f"[mock] lượt nói {self._turns} của khách"))
                self._reply_task = asyncio.create_task(self._reply(self._turns))

    async def greet(self) -> None:
        """Speak first like the real providers do for an inbound call."""
        self._reply_task = asyncio.create_task(self._speak("[mock] Dạ, showroom xin nghe, em là trợ lý AI."))

    async def _speak(self, text: str) -> None:
        await self._queue.put(OutputTranscript(text))
        audio = _tone(1200)
        step = int(OUT_RATE * CHUNK_MS / 1000) * 2
        for i in range(0, len(audio), step):
            await self._queue.put(AudioOut(audio[i : i + step]))
            await asyncio.sleep(CHUNK_MS / 1000 / 4)  # faster than real time, like a real model
        await self._queue.put(Usage(120, 80, 40, {"prompt": {"AUDIO": 80}, "response": {"AUDIO": 40}}))
        await self._queue.put(TurnComplete())

    async def _reply(self, turn: int) -> None:
        await asyncio.sleep(0.25)  # pretend model latency
        if turn % 2 == 0 and self.spec.tools:
            self._tool_wait = asyncio.get_running_loop().create_future()
            await self._queue.put(
                ToolCall(
                    call_id=f"mock-{turn}",
                    name="check_available_slots",
                    args={"date": (date.today() + timedelta(days=1)).isoformat()},
                )
            )
            await self._tool_wait
        await self._speak("[mock] Dạ, em là trợ lý AI thử nghiệm.")

    async def send_tool_results(self, results: list[ToolResult]) -> None:
        if self._tool_wait and not self._tool_wait.done():
            self._tool_wait.set_result(results)

    async def events(self) -> AsyncIterator[Event]:
        while True:
            ev = await self._queue.get()
            if ev is None:
                return
            yield ev

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reply_task:
            self._reply_task.cancel()
        await self._queue.put(None)


class MockLiveProvider:
    name = "mock"
    model = "mock"

    async def open(self, spec: SessionSpec) -> MockLiveSession:
        session = MockLiveSession(spec)
        await session.greet()
        return session
