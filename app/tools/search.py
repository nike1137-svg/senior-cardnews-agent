"""웹 검색 도구 (Tavily). 읽기 전용.

실패 규칙: 결과 0건이면 검색어를 바꿔 2회 재시도 → 그래도 없으면 사람에게 질문.
"기간을 넓힐까요?" 는 에이전트가 아니라 **사람이 정한다**.
"""

from __future__ import annotations

import asyncio

from app.config import get_settings
from app.tools import faults
from app.tools.base import Failure, OnFail, Permission, Tool, ToolResult, registry

PARAMS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "검색어. 한국어로 쓴다. 예) '시니어 건강 9월 독감 예방접종'",
        },
        "days": {
            "type": "integer",
            "description": "며칠 이내 자료를 찾을지. 기본 7. 자료가 부족하면 30까지 넓힐 수 있다.",
            "default": 7,
        },
        "max_results": {
            "type": "integer",
            "description": "가져올 최대 건수. 기본 10.",
            "default": 10,
        },
    },
    "required": ["query"],
}

DESCRIPTION = (
    "웹에서 최근 소식을 찾는다. 카드뉴스에 실을 후보를 모을 때 가장 먼저 쓴다. "
    "제목·링크·게시일·요약을 돌려준다. "
    "요약만 보고 사실로 단정하지 말 것 — 확인은 fetch_article 로 원문을 열어서 한다. "
    "결과가 부족하면 days 를 늘리거나 검색어를 바꿔 다시 부른다."
)


async def _search(query: str, days: int = 7, max_results: int = 10) -> ToolResult:
    if faults.should_fail("search_empty"):
        return ToolResult(ok=False, summary="[주입된 실패] 검색 결과 0건",
                          error_label=Failure.SEARCH_EMPTY)

    key = get_settings().tavily_api_key
    if not key:
        return ToolResult(ok=False, summary="TAVILY_API_KEY 가 없다",
                          error_label=Failure.TOOL_ERROR)

    from tavily import TavilyClient

    def call():
        client = TavilyClient(api_key=key)
        return client.search(query=query, topic="news", days=days,
                             max_results=max_results, search_depth="basic")

    raw = await asyncio.to_thread(call)
    items = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "published": r.get("published_date", ""),
            "snippet": (r.get("content", "") or "")[:400],
        }
        for r in (raw.get("results") or [])
    ]

    if not items:
        return ToolResult(ok=False, summary=f"'{query}' 검색 결과 0건 (최근 {days}일)",
                          error_label=Failure.SEARCH_EMPTY)

    return ToolResult(
        ok=True,
        data=items,
        summary=f"검색어='{query}' 최근 {days}일 → {len(items)}건",
    )


web_search = registry.add(Tool(
    name="web_search",
    description=DESCRIPTION,
    parameters=PARAMS,
    handler=_search,
    permission=Permission.READ,
    on_fail=OnFail.ASK_HUMAN,   # 0건이면 사람에게 "기간을 넓힐까요?" 를 묻는다
    max_retry=2,
))
