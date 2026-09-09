"""두뇌 LLM 어댑터 (D-010).

제공자를 설정 한 줄로 바꾼다. 루프 코드는 어느 쪽인지 몰라도 된다.

  base.py     공통 자료형 — ToolSpec / Message / LLMResult
  pricing.py  모델별 단가표
  budget.py   호출 수·비용 상한. LLM 으로 가는 유일한 관문
  redact.py   프롬프트에 키가 섞이지 않게 거르는 필터 (9번 규칙)
  gemini.py   Gemini 2.5 Flash  (기본, 무료)
  openai.py   GPT-5 mini        (비교·시연, 기관 크레딧 $5)
"""

from __future__ import annotations

from app.config import get_settings
from app.llm.base import LLMAdapter, LLMResult, Message, ToolCall, ToolSpec, Usage
from app.llm.budget import BudgetExceeded, BudgetGuard

__all__ = [
    "LLMAdapter",
    "LLMResult",
    "Message",
    "ToolCall",
    "ToolSpec",
    "Usage",
    "BudgetExceeded",
    "BudgetGuard",
    "get_adapter",
]


def get_adapter(
    provider: str | None = None,
    model: str | None = None,
    run_id: str | None = None,
) -> LLMAdapter:
    """설정에 적힌 제공자로 어댑터를 만든다."""
    name = (provider or get_settings().llm_provider).lower()

    if name == "gemini":
        from app.llm.gemini import GeminiAdapter

        return GeminiAdapter(model=model, run_id=run_id)

    if name == "openai":
        from app.llm.openai import OpenAIAdapter

        return OpenAIAdapter(model=model, run_id=run_id)

    raise ValueError(f"모르는 LLM 제공자: {name!r} (gemini | openai)")
