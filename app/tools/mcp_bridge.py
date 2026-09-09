"""자체 MCP 서버를 앱의 도구로 연결한다 (⭐확장3).

서버를 stdio 로 띄워 도구 목록을 받아오고, **우리 레지스트리에 그대로 등록**한다.
에이전트 입장에서는 web_search 나 get_weather 와 구분 없이 똑같이 부른다.

**세션을 오래 붙들지 않고 호출마다 짧게 연다.**
붙들어 두면 anyio 취소 범위가 태스크 경계를 넘나들어 깨진다
("Attempted to exit cancel scope in a different task"). 배경 루프와 웹 요청이
서로 다른 태스크에서 도는 구조라 그 문제가 실제로 났다.
호출당 0.5~1초가 더 들지만 한 실행에 몇 번 부르지 않는다.

붙지 않아도 앱은 돈다. MCP 도구가 없으면 에이전트는 나머지 도구로 진행한다.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.tools.base import Failure, OnFail, Permission, Tool, ToolResult, registry

log = logging.getLogger("tools.mcp")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SERVER_ARGS = ["-m", "mcp_server.server"]

# 쓰기 권한이 필요한 도구. 나머지는 읽기 전용으로 등록한다.
_WRITERS = {"record_publication"}


def _summarize(payload: Any, limit: int = 500) -> str:
    if isinstance(payload, str):
        return payload[:limit]
    try:
        return json.dumps(payload, ensure_ascii=False)[:limit]
    except Exception:  # noqa: BLE001
        return str(payload)[:limit]


def _params():
    from mcp import StdioServerParameters

    return StdioServerParameters(command=sys.executable, args=SERVER_ARGS, cwd=str(BASE_DIR))


def _schema_of(spec) -> dict:
    """MCP 1.x 는 inputSchema, 2.x 는 input_schema 로 준다."""
    return (getattr(spec, "input_schema", None)
            or getattr(spec, "inputSchema", None)
            or {"type": "object", "properties": {}})


def _parse(res) -> tuple[bool, Any]:
    data: Any = getattr(res, "structuredContent", None) or getattr(res, "structured_content", None)
    if data is None:
        chunks = [getattr(c, "text", "") for c in (getattr(res, "content", None) or [])]
        joined = "\n".join(x for x in chunks if x)
        try:
            data = json.loads(joined)
        except (json.JSONDecodeError, TypeError):
            data = joined
    is_error = bool(getattr(res, "isError", False) or getattr(res, "is_error", False))
    return (not is_error), data


def _make_handler(name: str):
    async def handler(**kwargs) -> ToolResult:
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client

            async with stdio_client(_params()) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    res = await session.call_tool(name, kwargs)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, summary=f"MCP 호출 실패({type(exc).__name__}): {exc}",
                              error_label=Failure.TOOL_ERROR)

        ok, data = _parse(res)
        return ToolResult(ok=ok, data=data, summary=_summarize(data),
                          error_label=None if ok else Failure.TOOL_ERROR)

    return handler


async def discover() -> list[str]:
    """서버에 한 번 붙어 도구 목록을 받아 등록한다. 실패해도 예외를 던지지 않는다."""
    try:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        async with stdio_client(_params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                specs = list(listed.tools)
    except Exception:  # noqa: BLE001 - MCP 가 없어도 앱은 돌아야 한다
        log.exception("MCP 서버 연결 실패 — 나머지 도구로 진행합니다")
        return []

    names = []
    for spec in specs:
        registry.add(Tool(
            name=spec.name,
            description=(spec.description or "").strip(),
            parameters=_schema_of(spec),
            handler=_make_handler(spec.name),
            permission=Permission.WRITE_OUTPUT if spec.name in _WRITERS else Permission.READ,
            on_fail=OnFail.SKIP,   # 운영 데이터가 없어도 카드뉴스는 만들 수 있다
            max_retry=1,
        ))
        names.append(spec.name)

    log.info("MCP 도구 %d개 등록: %s", len(names), names)
    return names
