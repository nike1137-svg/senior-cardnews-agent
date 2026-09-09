"""세팅을 바꿔 가며 같은 지점까지 돌려 비교한다 (루브릭 4번).

    uv run python scripts/compare_settings.py

같은 주제·같은 지역으로 **모델만 바꿔** 첫 사람 개입 지점까지 돌린다.
그 지점까지 무엇을 몇 번 호출했고 토큰을 얼마나 썼는지가 비교 대상이다.

끝까지 돌리지 않는 이유: 무료 한도가 모델당 하루 20회다 (D-016).
비교에 필요한 건 **같은 조건에서의 판단**이지 완주 여부가 아니다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.agent import state, trace  # noqa: E402
from app.agent.loop import AgentLoop  # noqa: E402
from app.db import init_db  # noqa: E402
from app.tools import mcp_bridge  # noqa: E402

TOPIC = "시니어 환절기 건강 관리"
REGION = "서울 노원구"

MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]


async def one(model: str) -> dict:
    run_id = state.create_run(TOPIC, REGION, "gemini", model)
    await AgentLoop(run_id).run_until_blocked(max_ticks=8)
    trace.export(run_id)
    o = trace.build_outcome(run_id)
    obs = state.observations(run_id)
    return {
        "model": model,
        "run_id": run_id,
        "tools": [f"{x['tool_name']}{'' if x['ok'] else '(실패)'}" for x in obs],
        "loop": o["loop_count"],
        "tokens": o["prompt_tokens"],
        "completion": o["completion_tokens"],
        "asked": o["human_interventions"],
        "status": o["status"],
    }


async def main() -> None:
    init_db()
    await mcp_bridge.discover()

    rows = []
    for m in MODELS:
        print(f"[{m}] 실행 중...", flush=True)
        try:
            rows.append(await one(m))
        except Exception as exc:  # noqa: BLE001
            print(f"  실패: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
        await asyncio.sleep(2)

    print("\n=== 같은 주제, 모델만 바꿔 첫 개입 지점까지 ===")
    print(f"{'모델':24s} {'루프':>4s} {'입력토큰':>8s} {'출력':>6s} {'질문':>4s}  도구 호출 순서")
    for r in rows:
        print(f"{r['model']:24s} {r['loop']:4d} {r['tokens']:8,d} {r['completion']:6,d} "
              f"{r['asked']:4d}  {' → '.join(r['tools'])}")


if __name__ == "__main__":
    asyncio.run(main())
