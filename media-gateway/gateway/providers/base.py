"""Provider-neutral live session contract.

The gateway never touches SDK objects outside an adapter: adapters translate provider messages into
these events. Audio in is PCM16 16 kHz, audio out is PCM16 at `output_rate` (Gemini: 24 kHz).
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema


@dataclass
class SessionSpec:
    system_instruction: str
    tools: list[ToolSpec] = field(default_factory=list)


# --- events emitted by a live session ---


@dataclass
class AudioOut:
    data: bytes


@dataclass
class InputTranscript:
    text: str


@dataclass
class OutputTranscript:
    text: str


@dataclass
class ToolCall:
    call_id: str
    name: str
    args: dict


@dataclass
class ToolCallCancelled:
    call_ids: list[str]


@dataclass
class Interrupted:
    pass


@dataclass
class TurnComplete:
    pass


@dataclass
class SpeechStarted:  # provider-side VAD, when the provider exposes it
    pass


@dataclass
class SpeechEnded:
    pass


@dataclass
class Usage:
    total_tokens: int
    prompt_tokens: int
    response_tokens: int
    by_modality: dict[str, dict[str, int]]  # {"prompt": {"AUDIO": n}, "response": {...}}


@dataclass
class Reconnected:
    reason: str


@dataclass
class SessionError:
    message: str
    fatal: bool


Event = (
    AudioOut
    | InputTranscript
    | OutputTranscript
    | ToolCall
    | ToolCallCancelled
    | Interrupted
    | TurnComplete
    | SpeechStarted
    | SpeechEnded
    | Usage
    | Reconnected
    | SessionError
)


@dataclass
class ToolResult:
    call_id: str
    name: str
    response: dict[str, Any]


class LiveSession(Protocol):
    output_rate: int

    async def send_audio(self, pcm16_16k: bytes) -> None: ...

    async def send_tool_results(self, results: list[ToolResult]) -> None: ...

    def events(self) -> AsyncIterator[Event]: ...

    async def close(self) -> None: ...


class LiveProvider(Protocol):
    name: str

    async def open(self, spec: SessionSpec) -> LiveSession: ...
