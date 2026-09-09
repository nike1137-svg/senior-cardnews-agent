"""원문 조회 도구 (httpx + trafilatura). 읽기 전용, 완전 무료.

**이 도구가 있는 이유가 루브릭에 직접 걸려 있다.**
강의 자료와 루브릭 모두 "검색 결과 요약만 보고 검증 완료 처리" 를 함정으로 꼽는다.
원문을 열어 제목·날짜를 직접 대조해야 한다.

실패 규칙: 페이지를 못 열면 그 항목을 **'미확인'으로 분류하고 계속 간다.**
조용히 버리지 않는다 — 버리면 사람이 확인할 기회가 사라진다.
"""

from __future__ import annotations

import httpx

from app.tools import faults
from app.tools.base import Failure, OnFail, Permission, Tool, ToolResult, registry

PARAMS = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "열어볼 기사 원문 주소"},
        "max_chars": {
            "type": "integer",
            "description": "가져올 본문 최대 글자 수. 기본 4000.",
            "default": 4000,
        },
    },
    "required": ["url"],
}

DESCRIPTION = (
    "기사 원문을 직접 열어 본문·제목·게시일을 가져온다. "
    "web_search 의 요약만으로 사실을 확정하지 말고, 카드에 실을 날짜·수치는 반드시 이 도구로 대조한다. "
    "열리지 않으면 그 항목은 '미확인'으로 분류하고 계속 진행한다."
)

_UA = "Mozilla/5.0 (compatible; senior-cardnews-agent/0.1)"


async def _fetch(url: str, max_chars: int = 4000) -> ToolResult:
    if faults.should_fail("fetch_fail"):
        return ToolResult(ok=False, summary=f"[주입된 실패] 원문 열기 실패: {url}",
                          error_label=Failure.TOOL_ERROR)

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                     headers={"User-Agent": _UA}) as client:
            resp = await client.get(url)
        if resp.status_code >= 400:
            return ToolResult(ok=False, summary=f"HTTP {resp.status_code} — 미확인 처리: {url}",
                              error_label=Failure.TOOL_ERROR)
        html = resp.text
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, summary=f"열기 실패({type(exc).__name__}) — 미확인 처리: {url}",
                          error_label=Failure.TOOL_ERROR)

    import trafilatura

    text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    title, published = "", ""
    try:
        meta = trafilatura.extract_metadata(html)
        title = getattr(meta, "title", "") or ""
        published = getattr(meta, "date", "") or ""
    except Exception:  # noqa: BLE001 - 메타데이터는 없어도 본문만 있으면 된다
        pass

    if not text.strip():
        return ToolResult(ok=False, summary=f"본문 추출 실패 — 미확인 처리: {url}",
                          error_label=Failure.TOOL_ERROR)

    body = text[:max_chars]
    return ToolResult(
        ok=True,
        data={"url": url, "title": title, "published": published, "text": body},
        summary=f"원문 확인: '{title[:40]}' 게시일={published or '미상'} 본문 {len(body)}자",
    )


fetch_article = registry.add(Tool(
    name="fetch_article",
    description=DESCRIPTION,
    parameters=PARAMS,
    handler=_fetch,
    permission=Permission.READ,
    on_fail=OnFail.SKIP,     # 못 열면 '미확인' 으로 두고 계속 간다
    max_retry=1,
))
