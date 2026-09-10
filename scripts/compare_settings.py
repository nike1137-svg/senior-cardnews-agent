"""세팅을 바꿔 가며 같은 지점까지 돌려 비교한다.

    uv run python scripts/compare_settings.py            # 기본 1회씩
    uv run python scripts/compare_settings.py --repeat 3 # 같은 세팅을 3회씩

같은 주제·같은 지역으로 **세팅만 바꿔** 첫 사람 개입 지점까지 돌린다.
그 지점까지 무엇을 몇 번 호출했고 토큰을 얼마나 썼는지가 비교 대상이다.

끝까지 돌리지 않는 이유: 무료 한도가 모델당 하루 20회다 (D-016).
비교에 필요한 건 **같은 조건에서의 판단**이지 완주 여부가 아니다.

**같은 세팅을 여러 번 돌리는 이유** (`--repeat`)
한 번씩만 재면 모델 간 차이인지 그날의 운인지 구분할 수 없다.
LLM 은 같은 입력에도 다르게 답하므로, 반복 없이 비교하면 편차를 실력으로 착각한다.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

try:
    sys.stdout.reconfigure(encoding="utf-8")   # 한국어 윈도우 콘솔(cp949) 대비
except (AttributeError, OSError):
    pass

from app.agent import state, trace  # noqa: E402
from app.agent.loop import AgentLoop  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import init_db  # noqa: E402
from app.tools import mcp_bridge  # noqa: E402

TOPIC = "시니어 환절기 건강 관리"
REGION = "서울 노원구"

# (제공자, 모델). 제공자를 섞을 수 있어야 "모델을 바꿨다" 가 아니라
# "제공자를 바꿨다" 까지 비교된다 — D-010 이 원래 계획한 것이다.
# OpenAI 는 키가 없으면 자동으로 건너뛴다.
SETTINGS: list[tuple[str, str]] = [
    ("gemini", "gemini-3.5-flash"),
    ("gemini", "gemini-3.5-flash-lite"),
    ("gemini", "gemini-3.1-flash-lite"),
    ("openai", "gpt-5-mini"),
]


def _available(settings_list: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """키가 없는 제공자는 조용히 빼지 않고 이유를 밝히고 뺀다."""
    s = get_settings()
    keys = {"gemini": s.gemini_api_key, "openai": s.openai_api_key}
    out = []
    for provider, model in settings_list:
        if keys.get(provider):
            out.append((provider, model))
        else:
            print(f"  건너뜀: {provider}/{model} — {provider.upper()}_API_KEY 가 없다", flush=True)
    return out


async def one(provider: str, model: str) -> dict:
    run_id = state.create_run(TOPIC, REGION, provider, model)
    await AgentLoop(run_id).run_until_blocked(max_ticks=8)
    trace.export(run_id)
    o = trace.build_outcome(run_id)
    obs = state.observations(run_id)
    return {
        "label": f"{provider}/{model}",
        "run_id": run_id,
        "tools": [f"{x['tool_name']}{'' if x['ok'] else '(실패)'}" for x in obs],
        "loop": o["loop_count"],
        "tokens": o["prompt_tokens"],
        "completion": o["completion_tokens"],
        "asked": o["human_interventions"],
        "status": o["status"],
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1,
                    help="같은 세팅을 몇 번씩 돌릴지 (편차 확인용)")
    ap.add_argument("--only", default="",
                    help="이 제공자만 돌린다 (gemini | openai). "
                         "이미 잰 쪽을 다시 돌려 무료 한도를 태우지 않으려고 둔다")
    args = ap.parse_args()

    init_db()
    await mcp_bridge.discover()

    wanted = SETTINGS
    if args.only:
        wanted = [(p, m) for p, m in SETTINGS if p == args.only]
        if not wanted:
            print(f"'{args.only}' 에 해당하는 세팅이 없다. "
                  f"있는 것: {sorted({p for p, _ in SETTINGS})}")
            return
    targets = _available(wanted)
    if not targets:
        print("돌릴 세팅이 없다. 키를 먼저 넣어라.")
        return

    rows: list[dict] = []
    for provider, model in targets:
        for i in range(args.repeat):
            tag = f"{provider}/{model}" + (f" ({i + 1}/{args.repeat})" if args.repeat > 1 else "")
            print(f"[{tag}] 실행 중...", flush=True)
            try:
                r = await one(provider, model)
                r["try"] = i + 1
                rows.append(r)
            except Exception as exc:  # noqa: BLE001
                # 실패도 기록으로 남긴다. 한도 소진이 곧 결과다.
                print(f"  실패: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            await asyncio.sleep(2)

    print("\n=== 같은 주제, 세팅만 바꿔 첫 개입 지점까지 ===")
    print(f"{'세팅':28s} {'회':>2s} {'루프':>4s} {'입력토큰':>8s} {'출력':>6s} {'질문':>4s}  도구 호출 순서")
    for r in rows:
        print(f"{r['label']:28s} {r.get('try', 1):2d} {r['loop']:4d} {r['tokens']:8,d} "
              f"{r['completion']:6,d} {r['asked']:4d}  {' → '.join(r['tools'])}")

    if args.repeat > 1:
        print("\n=== 세팅별 편차 (반복 측정) ===")
        print(f"{'세팅':28s} {'n':>2s} {'루프 평균':>9s} {'루프 폭':>7s} {'입력토큰 평균':>13s}")
        for provider, model in targets:
            label = f"{provider}/{model}"
            got = [r for r in rows if r["label"] == label]
            if not got:
                continue
            loops = [r["loop"] for r in got]
            toks = [r["tokens"] for r in got]
            spread = max(loops) - min(loops)
            print(f"{label:28s} {len(got):2d} {statistics.mean(loops):9.1f} "
                  f"{spread:7d} {statistics.mean(toks):13,.0f}")
        print("\n같은 세팅인데 루프 폭이 크면, 모델 간 차이를 논하기 전에 편차를 먼저 봐야 한다.")


if __name__ == "__main__":
    asyncio.run(main())
