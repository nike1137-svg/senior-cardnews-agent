"""시각을 사람에게 보여줄 때 쓰는 변환 한 곳.

**저장은 UTC, 표시는 한국 시간.** 둘을 섞지 않는다.

DB 에 UTC 로 쌓는 것은 맞다 — 기계가 비교하고 정렬할 값이고, 기기의 시간대 설정에
좌우되면 안 된다(`app/llm/budget.py` 의 `utc_now`). 문제는 그 값을 화면에
그대로 내보낸 것이었다. 담당자가 낮 12시 40분에 만든 실행이 `03:40` 으로 보이면
자기 기록이 아닌 것처럼 읽힌다.

카드 안에 들어가는 날짜는 여기를 거치지 않는다. 날씨 도구가 Open-Meteo 에
`timezone=Asia/Seoul` 로 요청해 처음부터 한국 날짜를 받는다(`app/tools/weather.py`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def to_kst(utc_text: str | None, fmt: str = "%m-%d %H:%M") -> str:
    """`'2026-09-10 03:40:36'` (UTC) → `'09-10 12:40'` (KST).

    모양이 다르거나 비어 있으면 손대지 않는다 — 화면 하나 때문에
    실행 기록 전체가 안 뜨는 쪽이 더 나쁘다.
    """
    if not utc_text:
        return "—"
    try:
        dt = datetime.strptime(str(utc_text)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(utc_text)
    return dt.replace(tzinfo=timezone.utc).astimezone(KST).strftime(fmt)
