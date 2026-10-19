"""Agent configuration schema, validation and hashing (plan/docs/01 Agents, AC04, AC25).

A published version is immutable; calls and eval results are tied to a config hash so an eval of one draft
can never be used to publish a different one.
"""

import hashlib
import json
import string
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TOOLS = ("check_available_slots", "create_appointment", "request_handoff")
PROMPT_VARS = {"business_name", "today", "weekday", "now_time", "timezone", "greeting"}
GREETING_VARS = {"business_name"}

DEFAULT_GREETING = (
    "Dạ, {business_name} xin nghe. Em là trợ lý AI, cuộc gọi được ghi âm để phục vụ anh/chị tốt hơn. "
    "Em có thể giúp gì ạ?"
)
DEFAULT_INSTRUCTIONS = (Path(__file__).parent / "receptionist.vi.md").read_text(encoding="utf-8")


def _placeholders(template: str) -> set[str]:
    try:
        return {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}
    except ValueError as exc:  # unbalanced braces
        raise ValueError(f"Dấu ngoặc nhọn không hợp lệ: {exc}") from exc


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instructions: str = Field(min_length=50, max_length=20000)
    greeting: str = Field(min_length=10, max_length=500)
    business_name: str = Field(min_length=1, max_length=120)
    provider: Literal["openai", "gemini"] = "openai"
    voice: str = Field(default="marin", max_length=40)
    tools: list[Literal["check_available_slots", "create_appointment", "request_handoff"]] = Field(
        default_factory=lambda: list(TOOLS)
    )
    vad_silence_ms: int = Field(default=600, ge=300, le=2000)
    eval_max_p95_ms: int = Field(default=2000, ge=500, le=10000)

    @field_validator("instructions")
    @classmethod
    def _instructions_vars(cls, v: str) -> str:
        unknown = _placeholders(v) - PROMPT_VARS
        if unknown:
            allowed = ", ".join("{" + x + "}" for x in sorted(PROMPT_VARS))
            raise ValueError(f"Biến không hỗ trợ: {', '.join(sorted(unknown))}. Chỉ dùng: {allowed}")
        return v

    @field_validator("greeting")
    @classmethod
    def _greeting_vars(cls, v: str) -> str:
        if _placeholders(v) - GREETING_VARS:
            raise ValueError("Lời chào chỉ được dùng biến {business_name}")
        return v

    @field_validator("tools")
    @classmethod
    def _unique_tools(cls, v: list[str]) -> list[str]:
        return sorted(set(v))


def config_hash(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def compliance_problems(config: AgentConfig) -> list[str]:
    """Greeting must disclose the AI and the recording before a version can go live (plan/docs/09)."""
    g = config.greeting.lower()
    problems = []
    if "ai" not in g.split() and "trợ lý ai" not in g and "trí tuệ nhân tạo" not in g:
        problems.append("Lời chào phải nói rõ đây là trợ lý AI")
    if "ghi âm" not in g:
        problems.append("Lời chào phải thông báo cuộc gọi được ghi âm")
    return problems


def default_config(business_name: str) -> dict:
    return AgentConfig(
        instructions=DEFAULT_INSTRUCTIONS, greeting=DEFAULT_GREETING, business_name=business_name
    ).model_dump()
