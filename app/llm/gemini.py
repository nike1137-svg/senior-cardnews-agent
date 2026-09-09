"""Gemini 어댑터 (기본 두뇌, 무료 티어).

함수 호출을 지원하는 API 로 직접 호출한다.
`claude -p` / `opencode run` 같은 CLI 위임은 쓰지 않는다 — 내가 정의한 도구 스키마가
남지 않아 루브릭 2번의 증거가 약해진다 (D-010).
"""

from __future__ import annotations

from app.config import get_settings
from app.llm.base import LLMResult, Message, ToolCall, ToolSpec, Usage
from app.llm.budget import BudgetGuard
from app.llm.redact import redact


class GeminiAdapter:
    provider = "gemini"

    def __init__(self, model: str | None = None, run_id: str | None = None) -> None:
        from google import genai  # 무거우므로 지연 import

        s = get_settings()
        self.model = model or s.gemini_model
        key = s.gemini_api_key
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY 가 없다. Windows 환경변수 또는 .env 를 확인할 것"
            )
        self._client = genai.Client(api_key=key)
        self.budget = BudgetGuard(run_id)

    # ── 우리 자료형 -> Gemini 형식 ──────────────────────────
    def _to_contents(self, messages: list[Message]):
        from google.genai import types

        contents = []
        for m in messages:
            if m.role == "system":
                continue
            body = redact(m.content)
            if m.role == "tool":
                part = types.Part.from_function_response(
                    name=m.name or "tool",
                    response={"result": body},
                )
                contents.append(types.Content(role="user", parts=[part]))
            else:
                role = "model" if m.role == "assistant" else "user"
                contents.append(
                    types.Content(role=role, parts=[types.Part.from_text(text=body)])
                )
        return contents

    def _to_config(self, messages: list[Message], tools: list[ToolSpec] | None):
        from google.genai import types

        kwargs = {}
        system = "\n\n".join(redact(m.content) for m in messages if m.role == "system")
        if system:
            kwargs["system_instruction"] = system
        if tools:
            kwargs["tools"] = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters=t.parameters,
                        )
                        for t in tools
                    ]
                )
            ]
        return types.GenerateContentConfig(**kwargs) if kwargs else None

    # ── 호출 ────────────────────────────────────────────────
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
    ) -> LLMResult:
        self.budget.check()

        resp = await self._client.aio.models.generate_content(
            model=self.model,
            contents=self._to_contents(messages),
            config=self._to_config(messages, tools),
        )

        calls: list[ToolCall] = []
        for fc in getattr(resp, "function_calls", None) or []:
            calls.append(
                ToolCall(
                    name=fc.name,
                    arguments=dict(fc.args or {}),
                    call_id=getattr(fc, "id", None),
                )
            )

        # resp.text 는 function_call 파트가 섞이면 경고를 뱉는다. 직접 모은다.
        chunks: list[str] = []
        for cand in getattr(resp, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                t = getattr(part, "text", None)
                if t:
                    chunks.append(t)
        text = "".join(chunks)

        meta = getattr(resp, "usage_metadata", None)
        usage = Usage(
            prompt_tokens=getattr(meta, "prompt_token_count", 0) or 0,
            completion_tokens=getattr(meta, "candidates_token_count", 0) or 0,
        )
        usd = self.budget.record(self.provider, self.model, usage)

        return LLMResult(
            text=text,
            tool_calls=calls,
            usage=usage,
            provider=self.provider,
            model=self.model,
            usd=usd,
        )
