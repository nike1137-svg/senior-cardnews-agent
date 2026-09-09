"""OpenAI 어댑터 (비교·시연용).

🔴 기관 지급 크레딧 $5 를 쓴다. BudgetGuard 가 1회 $0.30 / 누적 $3.00 에서 멈춘다.
   계정에 결제수단이 걸려 있으면 초과분이 기관에 청구되므로, 대시보드의 Usage limits
   확인은 이것과 **별개로** 해야 한다 (PRD 9장 5번).
"""

from __future__ import annotations

import json

from app.config import get_settings
from app.llm.base import LLMResult, Message, ToolCall, ToolSpec, Usage
from app.llm.budget import BudgetGuard
from app.llm.redact import redact


class OpenAIAdapter:
    provider = "openai"

    def __init__(self, model: str | None = None, run_id: str | None = None) -> None:
        from openai import AsyncOpenAI  # 지연 import

        s = get_settings()
        self.model = model or s.openai_model
        key = s.openai_api_key
        if not key:
            raise RuntimeError("OPENAI_API_KEY 가 없다. .env 를 확인할 것")
        self._client = AsyncOpenAI(api_key=key)
        self.budget = BudgetGuard(run_id)

    def _to_messages(self, messages: list[Message]) -> list[dict]:
        out: list[dict] = []
        for m in messages:
            body = redact(m.content)
            if m.role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "content": body,
                        "tool_call_id": m.tool_call_id or (m.name or "tool"),
                    }
                )
            else:
                out.append({"role": m.role, "content": body})
        return out

    @staticmethod
    def _to_tools(tools: list[ToolSpec] | None):
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
    ) -> LLMResult:
        self.budget.check()

        kwargs: dict = {
            "model": self.model,
            "messages": self._to_messages(messages),
        }
        spec = self._to_tools(tools)
        if spec:
            kwargs["tools"] = spec

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message

        calls: list[ToolCall] = []
        for tc in getattr(choice, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            calls.append(ToolCall(name=tc.function.name, arguments=args, call_id=tc.id))

        u = getattr(resp, "usage", None)
        usage = Usage(
            prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(u, "completion_tokens", 0) or 0,
        )
        usd = self.budget.record(self.provider, self.model, usage)

        return LLMResult(
            text=choice.content or "",
            tool_calls=calls,
            usage=usage,
            provider=self.provider,
            model=self.model,
            usd=usd,
        )
