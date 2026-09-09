"""날씨 조회 도구 (Open-Meteo). 읽기 전용, **키 불필요·완전 무료**.

시니어 안내에서 날씨는 그 자체가 생활정보다 — 한파·폭염·비 오는 날 미끄럼 주의 같은 것.

실패 규칙: 응답이 없으면 **날씨 카드를 건너뛰고** 나머지로 진행한다. 로그에는 남긴다.
"""

from __future__ import annotations

import httpx

from app.tools import faults, regions
from app.tools.base import Failure, OnFail, Permission, Tool, ToolResult, registry

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

PARAMS = {
    "type": "object",
    "properties": {
        "region": {
            "type": "string",
            "description": "지역 이름. 예) '서울', '노원구', '부산 해운대구'",
        },
        "days": {
            "type": "integer",
            "description": "며칠치를 볼지. 기본 3, 최대 7.",
            "default": 3,
        },
    },
    "required": ["region"],
}

DESCRIPTION = (
    "지역의 앞으로 며칠 날씨를 가져온다. 기온·강수확률·날씨 상태를 돌려준다. "
    "시니어 안내에서는 한파·폭염·비 온 날 미끄럼 같은 생활 주의사항의 근거가 된다. "
    "날짜를 카드에 적을 때는 '내일' 대신 '9월 15일 월요일' 처럼 명시할 것. "
    "응답이 없으면 날씨 내용을 빼고 나머지로 진행한다."
)

# Open-Meteo weather_code → 우리말
CODE = {
    0: "맑음", 1: "대체로 맑음", 2: "구름 조금", 3: "흐림",
    45: "안개", 48: "짙은 안개",
    51: "이슬비", 53: "이슬비", 55: "이슬비",
    61: "비", 63: "비", 65: "강한 비",
    71: "눈", 73: "눈", 75: "많은 눈",
    80: "소나기", 81: "소나기", 82: "강한 소나기",
    95: "천둥번개", 96: "천둥번개", 99: "천둥번개",
}
WEEKDAY = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def _korean_date(iso: str) -> str:
    """'2026-09-15' → '9월 15일 월요일'. 시니어에게는 날짜를 명시한다."""
    from datetime import date

    y, m, d = (int(v) for v in iso.split("-"))
    return f"{m}월 {d}일 {WEEKDAY[date(y, m, d).weekday()]}"


async def _weather(region: str, days: int = 3) -> ToolResult:
    if faults.should_fail("weather_fail"):
        return ToolResult(ok=False, summary="[주입된 실패] 날씨 응답 없음 — 날씨 내용 건너뜀",
                          error_label=Failure.TOOL_ERROR)

    days = max(1, min(int(days or 3), 7))

    # 1순위: 내장 좌표표. 외부 지오코딩이 한국 지명에 틀린 답을 주기 때문이다.
    hit = regions.lookup(region)
    uncertain = False
    if hit:
        found, lat, lon = hit
    else:
        found, lat, lon, uncertain = region, None, None, True

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            if lat is None:
                # 2순위: 외부 지오코딩. 한국(KR)으로 제한하고 '확인 필요'로 표시한다.
                geo = (await client.get(GEO_URL, params={
                    "name": region, "count": 5, "language": "ko",
                    "format": "json", "countryCode": "KR",
                })).json()
                kr = [h for h in (geo.get("results") or [])
                      if h.get("country_code") == "KR"]
                if not kr:
                    return ToolResult(
                        ok=False,
                        summary=f"'{region}' 위치를 찾지 못함 (내장 표·외부 조회 모두 실패)",
                        error_label=Failure.TOOL_ERROR)
                place = kr[0]
                found, lat, lon = place.get("name", region), place["latitude"], place["longitude"]

            fc = (await client.get(FORECAST_URL, params={
                "latitude": lat,
                "longitude": lon,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                         "precipitation_probability_max",
                "timezone": "Asia/Seoul",
                "forecast_days": days,
            })).json()
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, summary=f"날씨 조회 실패({type(exc).__name__})",
                          error_label=Failure.TOOL_ERROR)

    daily = fc.get("daily") or {}
    dates = daily.get("time") or []
    if not dates:
        return ToolResult(ok=False, summary="날씨 응답이 비어 있음",
                          error_label=Failure.TOOL_ERROR)

    rows = []
    for i, iso in enumerate(dates):
        rows.append({
            "date": iso,
            "date_ko": _korean_date(iso),
            "sky": CODE.get((daily.get("weather_code") or [None])[i], "정보 없음"),
            "high": (daily.get("temperature_2m_max") or [None])[i],
            "low": (daily.get("temperature_2m_min") or [None])[i],
            "rain_pct": (daily.get("precipitation_probability_max") or [None])[i],
        })

    head = rows[0]
    note = " ⚠️위치 확인 필요(외부 조회)" if uncertain else ""
    return ToolResult(
        ok=True,
        data={"place": found, "asked": region, "uncertain": uncertain, "days": rows},
        summary=(f"{found} {head['date_ko']} {head['sky']} "
                 f"{head['low']}~{head['high']}도, 강수 {head['rain_pct']}%"
                 f" (총 {len(rows)}일){note}"),
    )


get_weather = registry.add(Tool(
    name="get_weather",
    description=DESCRIPTION,
    parameters=PARAMS,
    handler=_weather,
    permission=Permission.READ,
    on_fail=OnFail.SKIP,     # 날씨는 없어도 카드뉴스가 성립한다
    max_retry=1,
))
