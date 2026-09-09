"""Gemini 어댑터 (기본 두뇌, 무료 티어).

함수 호출을 지원하는 API 로 직접 호출한다.
`claude -p` / `opencode run` 같은 CLI 위임은 쓰지 않는다 — 내가 정의한 도구 스키마가
남지 않아 루브릭 2번의 증거가 약해진다 (D-010).
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.llm.base import LLMResult, Message, ToolCall, ToolSpec, Usage
from app.llm.budget import BudgetExceeded, BudgetGuard
from app.llm.redact import redact

log = logging.getLogger("llm.gemini")


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
    def _candidates(self) -> list[str]:
        """기본 모델 → 폴백 모델 순서. 중복은 뺀다."""
        s = get_settings()
        extra = [m.strip() for m in (s.gemini_fallback_models or "").split(",") if m.strip()]
        out, seen = [], set()
        for m in [self.model, *extra]:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        s = str(exc)
        return "429" in s or "RESOURCE_EXHAUSTED" in s

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
    ) -> LLMResult:
        self.budget.check()

        contents = self._to_contents(messages)
        config = self._to_config(messages, tools)

        # 무료 티어는 모델마다 하루 한도가 따로다. 하나가 막히면 다음으로 갈아탄다.
        resp, used, tried = None, None, []
        for model in self._candidates():
            try:
                resp = await self._client.aio.models.generate_content(
                    model=model, contents=contents, config=config)
                used = model
                break
            except Exception as exc:  # noqa: BLE001
                if not self._is_quota_error(exc):
                    raise
                tried.append(model)
                log.warning("%s 일일 한도 소진 — 다음 모델로 갈아탑니다", model)

        if resp is None:
            raise BudgetExceeded(
                "무료 티어 일일 한도 소진",
                f"시도한 모델: {', '.join(tried)}. 내일 초기화되거나 다른 키가 필요합니다",
            )

        if used != self.model:
            log.info("모델 대체: %s -> %s", self.model, used)

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
        # 실제로 응답한 모델로 기록한다. 대체됐는데 원래 모델로 남기면 평가표가 틀어진다.
        usd = self.budget.record(self.provider, used, usage)

        return LLMResult(
            text=text,
            tool_calls=calls,
            usage=usage,
            provider=self.provider,
            model=used,
            usd=usd,
        )
