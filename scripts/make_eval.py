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
from statistics import mean
from pathlib import Path

# 한국어 윈도우 콘솔은 기본이 cp949 라 '—' 같은 글자에서 UnicodeEncodeError 로 죽는다.
# 표는 다 쓰고 마지막 안내 한 줄에서 죽으므로 알아채기도 어렵다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

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


def variance(rows: list[dict]) -> str:
    """같은 세팅을 두 번 이상 잰 것만 모아 편차를 낸다.

    한 번씩만 재면 모델 간 차이인지 그날의 운인지 구분할 수 없다.
    LLM 은 같은 입력에도 다르게 답하므로, 반복 없이 비교하면 편차를 실력으로 착각한다.
    """
    # **설정한 세팅**(configured_model)으로 묶는다. 실제로 쓴 모델(model)로 묶으면
    # 한도 소진으로 폴백된 실행이 다른 세팅에 섞여, 바꾼 적 없는 세팅이 비교에 끼어든다.
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        setting = r.get("configured_model") or r.get("model", "")
        groups.setdefault((r.get("topic", ""), setting), []).append(r)

    repeated = {k: v for k, v in groups.items() if len(v) >= 2}
    if not repeated:
        return "_같은 세팅을 두 번 이상 잰 실행이 아직 없다._"

    by_topic: dict[str, list] = {}
    for (topic, model), g in repeated.items():
        by_topic.setdefault(topic, []).append((model, g))

    blocks = []
    for topic, items in by_topic.items():
        lines = [f"**주제: {topic}**", "",
                 "| 설정한 세팅 | n | 루프 평균 | 루프 폭 | 입력 토큰 평균 | 출력 토큰 평균 | 폴백 | 비용 |",
                 "|---|---|---|---|---|---|---|---|"]
        for model, g in sorted(items):
            loops = [x.get("loop_count", 0) for x in g]
            usd = sum(x.get("usd", 0) or 0 for x in g)
            # 설정한 모델과 실제로 쓴 모델이 다른 실행 수. 무료 한도에 걸린 흔적이다.
            fell = sum(1 for x in g
                       if (x.get("configured_model") or x.get("model")) != x.get("model"))
            lines.append(
                f"| `{model}` | {len(g)} | {mean(loops):.1f} | {max(loops) - min(loops)} "
                f"| {mean([x.get('prompt_tokens', 0) for x in g]):,.0f} "
                f"| {mean([x.get('completion_tokens', 0) for x in g]):,.0f} "
                f"| {f'{fell}/{len(g)}' if fell else '—'} "
                f"| {'무료' if usd == 0 else f'${usd:.4f}'} |")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


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
| **질문이 반복 예산을 먹음** | 카드 합성 단계에서 같은 것을 세 번 물어 루프 3회를 태웠다. 재시도 상한은 실패에만 걸리고 **질문은 무제한**이었다 | 단계별 질문 상한 3회 (D-023 후속) |
| **발송이 지어낸 파일명을 씀** | 실제는 `card_01.png` 인데 모델이 `card1.png` 을 불러 "보낼 파일이 없다" 로 막혔다 | 파일 목록을 앱이 폴더에서 직접 읽는다 |
| **상한 30 이 여전히 부족** | 세 실행이 연속으로 6/7 에서 상한에 걸렸다. 완주한 실행조차 27 로 90% 를 썼다 | 45 로 조정 (D-024). **원인부터 고치고 올렸다** |
| **검색 결과가 모델에 안 갔다** | `ToolResult.data` 가 쓰이지 않았다. 저장되는 요약은 `→ 3건` 처럼 **건수만**(48자) 적어, 다음 반복부터 모델은 URL 을 본 적이 없었다 | 요약에 `제목 (게시일) URL` 을 싣고, 관찰 절단 길이를 도구별로 뒀다 (D-022) |
| **게시일 표기가 깨졌다** | Tavily 가 RFC-2822 를 주는데 앞 10자를 잘라 `Wed, 02 Se` 가 됐다 | `YYYY-MM-DD` 로 정규화. **날짜 대조가 함정 1번**이다 (D-022) |
| **경고가 뒤 단계로 새어나갔다** | 호출 횟수를 실행 전체로 세니, 단계1 의 *"그만하고 finish_step 하라"* 가 단계3 에도 실려 원문을 열기 전에 종료됐다 | 단계 안에서만 센다 (D-023) |
| 🔴 **게이트가 앞 단계 답변으로 충족됐다** | *"이미 답을 받았다면"* 이 어느 질문인지 구분하지 않아, 단계2(후보 선택)가 **질문 없이** 통과됐다. 단계4 는 물었다 — 비결정적으로 새는 구조 | 이 단계에서 물은 질문만 근거로 삼고, `finish_step` 을 **코드로 막았다** (D-023) |

앞의 다섯을 고친 뒤의 실행에서 **7/7 단계 완주**했다. 마지막 단계가 발송 승인이라
사람이 승인해야 `done` 이 되는 구조인 것도 맞다.

뒤의 일곱은 **완주한 뒤에 발견한 것들**이다. 돌아가는 것과 제대로 돌아가는 것은 다르다.
`run-ebec96b7eba9` 와, 완주를 다시 시도하며 얻은 네 실행에서 확인했다.

**완주는 세 번 실패하고 네 번째에 됐다.** 매번 다른 곳에서 막혔고, 막힌 자리마다 원인이 달랐다.

| 실행 | 루프 | 도달 | 막힌 이유 |
|---|---|---|---|
| `run-ca32f9d1e18d` | 30 | 5/7 | 같은 질문 3회 반복으로 예산 소진 |
| `run-4605c934a58e` | 30 | 6/7 | 발송이 지어낸 파일명을 찾다 실패 |
| `run-ce638ca65581` | 30 | 6/7 | 상한 자체가 부족 |
| **`run-e5484e2520c7`** | **27** | **7/7** | **완주** — 세 가지를 다 고친 뒤 |

```
단계2  ask_human → (사람 답변 2건) → finish     ← 이전에는 finish 만 하고 건너뜀
단계3  web_search FAIL(이 단계 불허)
       fetch_article OK  원문 563자 · 게시일 2026-09-04
       fetch_article OK  게시일 2026-08-16
       fetch_article OK  (재확인)
단계4  get_audience_profile → get_card_template → ask_human
```

**`fetch_article` 이 실제로 원문을 열고 게시일을 확인한 첫 실행이다.**
그전까지는 검색 결과 요약만 보고 넘어갔다 — 이 과제가 반복해서 경고한 함정 그대로였다.

## 2. 세팅 비교 — 제공자와 모델을 바꿔 가며

```bash
uv run python scripts/compare_settings.py --repeat 3          # 전부
uv run python scripts/compare_settings.py --only openai --repeat 3
```

같은 주제·지역으로 **세팅만 바꿔** 첫 사람 개입 지점까지 돌린 결과다.
끝까지 돌리지 않는 이유는 무료 한도(모델당 하루 20회, D-016) 때문이고,
비교에 필요한 건 **같은 조건에서의 판단**이지 완주 여부가 아니다.

### 같은 세팅을 3회씩 쟀다

한 번씩만 재면 **모델 간 차이인지 그날의 운인지 구분할 수 없다.**
LLM 은 같은 입력에도 다르게 답한다.

{variance(rows)}

### 무엇이 달랐나

- 🔴 **`gemini-3.5-flash` 행은 비교로 쓸 수 없다.** 폴백 열을 보면 4회 중 3회가
  한도 소진으로 **다른 모델로 갈아탔다.** 설정만 그 모델이었을 뿐 실제로는 lite 로 돌았다.
  **"모델을 설정했다" 와 "그 모델로 돌았다" 는 다르다.**
  폴백을 기록해두지 않았다면 이 표는 거짓말을 했을 것이다
- 🔺 **이전 결론을 하나 거둬들인다.** 1회씩 쟀을 때는 *"큰 모델이 도구를 더 쓴다"* 고 적었는데,
  반복해 보니 **lite 두 모델의 평균 차이가 각자의 편차 폭보다 작다.**
  모델 차이라고 말할 수 없다. **반복 없이 비교하면 편차를 실력으로 착각한다**
- **가장 일관된 것은 `gpt-5-mini` 였다** (폭 1). Gemini lite 계열은 폭 2~5 로 흔들렸다.
  운영에서는 평균보다 이 폭이 더 중요할 수 있다 — 매번 다르게 도는 것을 예측할 수 없다
- **제공자 간 차이가 모델 간 차이보다 컸다.** `gpt-5-mini` 는 출력 토큰이
  Gemini 계열의 8–10배다(3,300–4,000 vs 250–450). 추론 토큰을 쓰기 때문이다.
  반대로 입력 토큰은 적다 — 루프를 덜 돌아서다.
  **"토큰이 많다/적다" 는 제공자를 섞으면 같은 뜻이 아니다**
- **도구 선택 순서는 제공자를 가리지 않았다.** Gemini 3종과 OpenAI 모두
  `list_past_publications` 를 **가장 먼저** 불렀다. 단계 목표에 도구 이름을 직접 적어둔 것이
  제공자와 무관하게 작동했다 — D-022 에서 얻은 방법이다

### 비용과 한도

Gemini 는 무료 티어라 0원이고, OpenAI 는 기관 지급 크레딧 $5 에서 나간다.
비용 열은 `llm_usage` 에 쌓인 실제 사용량으로 계산한 값이다.

**공짜에는 값이 있다.** 무료 경로는 돈이 안 드는 대신 한도에 걸려
**측정 자체가 오염됐다**(위 폴백 3/4). 유료 경로는 $0.03 으로 3회를 흔들림 없이 쟀다.
무료를 기본으로 두는 판단(D-010)은 유지하되, **비교 실험만큼은 한도에 걸리지 않는 쪽으로
재야 한다**는 것을 이번에 배웠다.

### 실행별 원자료

{controlled(rows)}

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
