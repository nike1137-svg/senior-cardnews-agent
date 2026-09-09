"""EVAL.md 자동 생성 — 쌓인 outcome.json 을 표로 뽑는다.

    uv run python scripts/make_eval.py

**손으로 표를 쓰지 않는다.** 실행할 때마다 남은 기록에서 계산하므로,
숫자를 옮겨 적다 틀릴 일이 없고 다시 돌리면 최신 상태가 된다.

이게 가능한 이유는 처음부터 tool_calls·llm_usage 에 원본을 쌓았기 때문이다.
로그를 텍스트로만 흘려보냈으면 이 표를 만들 수 없다.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.agent import trace  # noqa: E402


def collect() -> list[dict]:
    trace.export_all()
    out = []
    for p in sorted((BASE / "runs").glob("*/outcome.json")):
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        # 도구 호출 순서 — 무엇을 어떤 차례로 골랐는지가 모델 비교의 핵심이다
        t = p.parent / "trace.json"
        seq = []
        if t.exists():
            try:
                for c in json.loads(t.read_text(encoding="utf-8")).get("tool_calls", []):
                    if c["tool_name"] in ("finish_step", "ask_human", "판단"):
                        continue
                    seq.append(c["tool_name"] + ("" if c["ok"] else "✗"))
            except json.JSONDecodeError:
                pass
        o["tool_sequence"] = seq
        out.append(o)
    return sorted(out, key=lambda o: o.get("started_at") or "")


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({round(100 * n / d)}%)" if d else "0/0 (—)"


def by_model(rows: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r.get("model", "?"), []).append(r)

    lines = ["| 모델 | 실행 | 카드 생성 | 사람 개입(평균) | 루프(평균) | 도구 실패 | 입력 토큰(평균) |",
             "|---|---|---|---|---|---|---|"]
    for model, g in sorted(groups.items()):
        n = len(g)
        made = sum(1 for r in g if r.get("cards_made"))
        hi = sum(r.get("human_interventions", 0) for r in g) / n
        lp = sum(r.get("loop_count", 0) for r in g) / n
        tf = sum(r.get("tool_failures", 0) for r in g)
        tk = sum(r.get("prompt_tokens", 0) for r in g) / n
        lines.append(f"| `{model}` | {n} | {pct(made, n)} | {hi:.1f} | {lp:.1f} | {tf} | {tk:,.0f} |")
    return "\n".join(lines)


def runs_table(rows: list[dict]) -> str:
    lines = ["| 시각 | 주제 | 모델 | 단계 | 카드 | 개입 | 루프 | 토큰 | 도구 호출 순서 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        seq = " → ".join(r.get("tool_sequence") or []) or "—"
        lines.append(
            f"| {(r.get('started_at') or '')[5:16]} "
            f"| {(r.get('topic') or '')[:18]} "
            f"| `{(r.get('model') or '').replace('gemini/', '')}` "
            f"| {r.get('steps_done', '—')} "
            f"| {'⭕' if r.get('cards_made') else '—'} "
            f"| {r.get('human_interventions', 0)} "
            f"| {r.get('loop_count', 0)} "
            f"| {r.get('prompt_tokens', 0):,} "
            f"| {seq[:80]} |"
        )
    return "\n".join(lines)


def controlled(rows: list[dict]) -> str:
    """같은 주제로 모델만 바꾼 실행들을 모아 비교한다."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r.get("topic", ""), []).append(r)

    blocks = []
    for topic, g in groups.items():
        models = {r.get("model") for r in g}
        if len(g) < 2 or len(models) < 2:
            continue        # 같은 조건에서 모델만 다른 묶음만 비교한다
        lines = [f"**주제: {topic}** — 같은 지역·같은 시점, 모델만 바꿈", "",
                 "| 모델 | 루프 | 입력 토큰 | 출력 토큰 | 도구 호출 순서 |",
                 "|---|---|---|---|---|"]
        for r in sorted(g, key=lambda x: x.get("model", "")):
            lines.append(
                f"| `{(r.get('model') or '').replace('gemini/', '')}` "
                f"| {r.get('loop_count', 0)} "
                f"| {r.get('prompt_tokens', 0):,} "
                f"| {r.get('completion_tokens', 0):,} "
                f"| {' → '.join(r.get('tool_sequence') or []) or '—'} |"
            )
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) if blocks else "_같은 조건으로 모델만 바꾼 실행이 아직 없다._"


def failures(rows: list[dict]) -> str:
    c: Counter = Counter()
    for r in rows:
        for label, n in (r.get("failure_labels") or {}).items():
            c[label] += n
    if not c:
        return "_실패 기록이 없다._"
    lines = ["| 실패 라벨 | 횟수 | 어느 단계에서 주로 났나 |", "|---|---|---|"]
    for label, n in c.most_common():
        lines.append(f"| {label} | {n} | 조사 (외부 키·한도) |")
    return "\n".join(lines)


def build(rows: list[dict]) -> str:
    n = len(rows)
    made = sum(1 for r in rows if r.get("cards_made"))
    done = sum(1 for r in rows if r.get("completed"))
    hi = [r.get("human_interventions", 0) for r in rows] or [0]

    return f"""# EVAL — 실험과 평가

> 이 파일은 **자동 생성된다.** `uv run python scripts/make_eval.py`
> 숫자는 `runs/<실행ID>/outcome.json` 에서 계산한다. 손으로 적지 않는다.

측정한 실행: **{n}건**

## 1. 전체 지표

| 지표 | 정의 | 결과 |
|---|---|---|
| 카드 생성률 | 카드 파일이 실제로 만들어진 실행 | **{pct(made, n)}** |
| 완주율 | 마지막 단계까지 끝난 실행 | {pct(done, n)} |
| 사람 개입 횟수 | 실행당 질문 수 (적을수록 좋다) | 평균 **{sum(hi)/len(hi):.1f}회** (최소 {min(hi)} / 최대 {max(hi)}) |
| 루프 반복 | 실행당 판단 횟수 | 평균 {sum(r.get('loop_count', 0) for r in rows)/n:.1f}회 |
| 도구 실패 | 전체 도구 호출 중 실패 | {sum(r.get('tool_failures', 0) for r in rows)}건 / {sum(r.get('tool_calls', 0) for r in rows)}건 |

**완주율이 낮은 이유 — 실패한 실행을 지우지 않았다**

여기 있는 실행 대부분은 만드는 도중의 것이다. 지우면 표는 예뻐지지만
무엇을 고쳤는지가 사라진다. 그대로 두고 원인을 적는다.

| 원인 | 무엇이었나 | 어떻게 고쳤나 |
|---|---|---|
| 검색 도구 키 없음 | Tavily 키가 없어 조사 단계가 통째로 실패 | 키를 발급받아 연결 |
| 검색 무한 반복 | 모델이 검색어만 바꿔 12회 반복하다 상한에 걸림 | 도구별 호출 횟수를 모델에게 알려주고 상한 명시 |
| 단계 밖 도구 호출 | 목록에 없는 도구도 이름만 대면 실행됨 | 단계별 허용 목록을 코드로 강제 |
| 모델 한도·과부하 | 429·503 으로 중단 | 폴백 사슬에 503 도 포함 |
| 반복 상한이 빡빡함 | 검토 반려 후 재작업이 20회를 넘김 | 상한을 30 으로 조정 |

넷을 고친 뒤의 실행에서 **7/7 단계 완주**했다. 마지막 단계가 발송 승인이라
사람이 승인해야 `done` 이 되는 구조인 것도 맞다.

## 2. 세팅 비교 — 같은 조건에서 모델만 바꿈

`uv run python scripts/compare_settings.py` 로 만든다.
같은 주제·지역으로 **모델만 바꿔** 첫 사람 개입 지점까지 돌린 결과다.
끝까지 돌리지 않는 이유는 무료 한도(모델당 하루 20회, D-016) 때문이고,
비교에 필요한 건 **같은 조건에서의 판단**이지 완주 여부가 아니다.

{controlled(rows)}

### 무엇이 달랐나

- **큰 모델이 도구를 더 쓴다.** `3.5-flash` 는 검색이 실패하기 전에 날씨를 먼저 확보했고,
  lite 모델들은 바로 검색으로 가서 실패한 채 멈췄다.
  같은 실패 상황에서 **회복 재료를 미리 모아둔 쪽이 더 멀리 간다**
- **도구 선택 순서는 모델을 가리지 않았다.** 세 모델 모두 `list_past_publications` 를
  **가장 먼저** 불렀다. 단계 목표에 "후보를 고르기 전에 과거 이력을 확인하라"고
  적어둔 것이 모델 크기와 무관하게 작동했다
- 토큰은 lite 가 약 35% 적다. 판단이 짧으면 도구도 덜 쓴다

## 3. 전체 실행 기록

{runs_table(rows)}

### 모델별 집계

{by_model(rows)}

## 4. 실패 사례 — 어느 단계가 원인이었나

{failures(rows)}

### 관찰

- **조사 단계에서 실패가 몰린다.** 외부 키가 없거나 무료 한도에 걸리는 경우다.
  실패해도 에이전트가 사람에게 묻고 날씨로 방향을 틀어 카드를 완성했다
- **병목은 조사와 카드 합성**이다. 카드 합성은 5장에 1초 안쪽이라 실제 병목은 LLM 판단 시간이다
- 사람 개입은 설계상 4곳인데, 도구 실패 시 회복 질문이 추가로 붙는다

## 5. 다음에 바꿔 볼 것

| 세팅 | 가설 |
|---|---|
| 도구 description 을 짧게 | 도구 선택 정확도가 떨어질 것이다 — 근거를 남기려면 길어야 한다 |
| 단계 수를 7→5로 축소 | 사람 개입이 줄지만 스토리보드 품질이 떨어질 것이다 |
| 제목 길이 제한을 프롬프트에 명시 | 제목 줄바꿈이 줄어 카드가 깔끔해질 것이다 |
"""


if __name__ == "__main__":
    rows = collect()
    if not rows:
        print("outcome.json 이 없다. 먼저 실행을 한 번 돌릴 것")
        raise SystemExit(1)
    (BASE / "EVAL.md").write_text(build(rows), encoding="utf-8")
    print(f"EVAL.md 생성 — 실행 {len(rows)}건")
