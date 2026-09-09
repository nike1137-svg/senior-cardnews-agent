"""LLM 어댑터 공통 자료형.

제공자를 바꿔도 루프 코드는 그대로여야 한다 (D-010).
루브릭 2번이 요구하는 "도구의 입력·출력 스키마"는 ToolSpec 으로 표현한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolSpec:
    """에이전트가 쓸 수 있는 도구 하나의 정의.

    description 은 모델이 "언제 이 도구를 써야 하는지" 판단하는 근거다.
    루브릭이 명시적으로 요구하는 항목이라 대충 쓰지 않는다.
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema (type=object)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str | None = None


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class Message:
    role: Role
    content: str
    name: str | None = None          # role="tool" 일 때 도구 이름
    tool_call_id: str | None = None  # OpenAI 가 요구


@dataclass
class LLMResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    provider: str = ""
    model: str = ""
    usd: float = 0.0

    @property
    def wants_tool(self) -> bool:
        return bool(self.tool_calls)


@runtime_checkable
class LLMAdapter(Protocol):
    provider: str
    model: str

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
    ) -> LLMResult: ...
