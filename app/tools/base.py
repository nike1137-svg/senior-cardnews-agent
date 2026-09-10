"""도구 공통 틀.

도구 하나는 네 가지를 반드시 갖는다.

  1. 입력·출력 **스키마**          모델이 뭘 넣어야 하는지 안다
  2. **description**              모델이 언제 써야 하는지 안다
  3. **실패 처리 규칙**            재시도 / 대체 경로 / 중단 / 사람에게 질문
  4. **권한**                      읽기 전용인지, 어디에 쓸 수 있는지

실행은 전부 `run_tool()` 을 거친다. 여기서 소요 시간을 재고 `tool_calls` 에 남긴다.
화면 로그와 trace.json 이 전부 이 기록에서 나온다 — 도구마다 따로 적으면 빠진다.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from contextlib import closing
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.db import connect
from app.llm.base import ToolSpec
from app.llm.budget import utc_now
from app.llm.redact import redact


class Failure(str, Enum):
    """실패 라벨. 나중에 '어느 단계가 원인이었나' 를 표로 뽑는 근거가 된다."""

    SEARCH_EMPTY = "검색부실"
    FACT_ERROR = "사실오류"
    HALLUCINATION = "환각"
    HARD_WORDS = "문장어려움"
    IMAGE_FAILED = "이미지실패"
    TOOL_ERROR = "도구오류"
    TIMEOUT = "시간초과"
    GAVE_UP = "중간포기"


class OnFail(str, Enum):
    """실패했을 때 무엇을 할지. 도구마다 미리 정해 둔다."""

    RETRY = "재시도"
    FALLBACK = "대체경로"
    ASK_HUMAN = "사람에게질문"
    SKIP = "건너뛰기"
    STOP = "중단"


class Permission(str, Enum):
    READ = "읽기전용"
    WRITE_OUTPUT = "쓰기(output 폴더만)"
    EXTERNAL_SEND = "외부발송(승인필요)"


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    summary: str = ""
    error_label: Failure | None = None
    fallback_used: bool = False
    duration_ms: int = 0


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[ToolResult]]
    permission: Permission = Permission.READ
    on_fail: OnFail = OnFail.RETRY
    max_retry: int = 2
    needs_approval: bool = False        # 되돌릴 수 없는 작업인가
    fallback: Callable[..., Awaitable[ToolResult]] | None = None

    def spec(self) -> ToolSpec:
        """LLM 에게 넘길 형태. 스키마와 설명이 그대로 간다."""
        return ToolSpec(name=self.name, description=self.description,
                        parameters=self.parameters)


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self, names: list[str] | None = None) -> list[ToolSpec]:
        items = self._tools.values() if names is None else [
            self._tools[n] for n in names if n in self._tools
        ]
        return [t.spec() for t in items]

    def all(self) -> list[Tool]:
        return list(self._tools.values())


registry = Registry()


def log_call(run_id: str | None, step_no: int | None, tool_name: str, reason: str,
             args: dict, result: ToolResult) -> None:
    """실행 로그를 남긴다. 화면 패널과 trace.json 의 원본."""
    sql = (
        "INSERT INTO tool_calls "
        "(run_id, step_no, tool_name, reason, input_json, output_summary, ok, "
        " error_label, duration_ms, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
    )
    row = (
        step_no,
        tool_name,
        redact(reason or ""),
        redact(json.dumps(args, ensure_ascii=False)[:2000]),
        redact(result.summary or "")[:2000],
        1 if result.ok else 0,
        result.error_label.value if result.error_label else None,
        result.duration_ms,
        utc_now(),
    )
    with closing(connect()) as conn, conn:
        try:
            conn.execute(sql, (run_id, *row))
        except Exception:
            conn.execute(sql, (None, *row))


async def run_tool(tool: Tool, args: dict, *, run_id: str | None = None,
                   step_no: int | None = None, reason: str = "") -> ToolResult:
    """도구를 실행하고 결과를 기록한다.

    실패하면 도구가 미리 정해둔 규칙(on_fail)대로 움직인다.
    **"종료 코드 0" 을 성공으로 보지 않는다** — 도구가 스스로 ok 를 판정한다.
    """
    attempt = 0
    last: ToolResult

    while True:
        t0 = time.perf_counter()
        try:
            last = await tool.handler(**args)
        except Exception as exc:  # noqa: BLE001 - 어떤 도구든 죽이지 않는다
            last = ToolResult(ok=False, summary=f"{type(exc).__name__}: {exc}",
                              error_label=Failure.TOOL_ERROR)
        last.duration_ms = int((time.perf_counter() - t0) * 1000)

        if last.ok:
            break

        attempt += 1
        if tool.on_fail is OnFail.RETRY and attempt <= tool.max_retry:
            continue

        if tool.on_fail is OnFail.FALLBACK and tool.fallback and not last.fallback_used:
            t0 = time.perf_counter()
            try:
                alt = await tool.fallback(**args)
                alt.fallback_used = True
                alt.duration_ms = int((time.perf_counter() - t0) * 1000)
                alt.summary = f"[대체경로] {alt.summary}"
                last = alt
            except Exception as exc:  # noqa: BLE001
                last = ToolResult(ok=False, summary=f"대체경로 실패: {exc}",
                                  error_label=Failure.TOOL_ERROR,
                                  duration_ms=int((time.perf_counter() - t0) * 1000))
        break

    log_call(run_id, step_no, tool.name, reason, args, last)
    return last
