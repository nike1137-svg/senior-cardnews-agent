"""실패 주입 스위치.

**왜 필요한가**
실패·재시도 화면은 제출에 꼭 필요한 캡처인데(D-009), 실제 실패가 마침 그때 일어나야
찍을 수 있다. 그리고 코드에 적어만 두고 한 번도 안 돌려본 대체 경로는 실제로는 안 돌아간다.

환경변수 하나로 원하는 실패를 언제든 만든다.

    FAULT_INJECT=search_empty,image_fail

이건 시험용 장치이지 숨겨진 동작이 아니다. 켜져 있으면 화면과 로그에 그대로 표시한다.
"""

from __future__ import annotations

from app.config import get_settings

KNOWN = {
    "search_empty": "웹 검색이 0건을 돌려준다",
    "fetch_fail": "원문 조회가 실패한다",
    "weather_fail": "날씨 조회가 응답하지 않는다",
    "image_fail": "이미지 생성이 한도 초과로 거부된다",
    "line_fail": "발송이 실패한다",
}


def active() -> set[str]:
    raw = (get_settings().fault_inject or "").strip()
    if not raw:
        return set()
    return {p.strip() for p in raw.split(",") if p.strip()}


def should_fail(name: str) -> bool:
    return name in active()


def banner() -> str:
    """화면에 띄울 안내. 켜져 있는 걸 숨기지 않는다."""
    on = sorted(active())
    if not on:
        return ""
    items = ", ".join(f"{n}({KNOWN.get(n, '?')})" for n in on)
    return f"실패 주입이 켜져 있습니다 — {items}"
