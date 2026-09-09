"""에이전트가 호출할 도구 (루브릭 2번).

각 도구는 입출력 스키마 · description · 실패 처리 규칙 · 권한을 함께 정의한다.
이 모듈을 import 하면 registry 에 전부 등록된다.

  web_search      Tavily              읽기 전용     0건 → 사람에게 질문
  fetch_article   httpx+trafilatura   읽기 전용     실패 → '미확인' 으로 두고 계속
  get_weather     Open-Meteo          읽기 전용     실패 → 건너뛰고 진행
  compose_cards   Pillow              output/ 안만  실패 → 1회 재시도
  send_line       LINE                외부 발송     🔴 재시도 금지, 3중 잠금
"""

from __future__ import annotations

from app.tools.base import (  # noqa: F401
    Failure,
    OnFail,
    Permission,
    Tool,
    ToolResult,
    registry,
    run_tool,
)

# import 하는 것만으로 registry 에 등록된다
from app.tools import compose, fetch, line, search, weather  # noqa: F401,E402

__all__ = ["registry", "run_tool", "Tool", "ToolResult", "Failure", "OnFail", "Permission"]
