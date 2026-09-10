"""EVAL.md 자동 생성 — 쌓인 outcome.json 을 표로 뽑는다.

    uv run python scripts/make_eval.py

**손으로 표를 쓰지 않는다.** 실행할 때마다 남은 기록에서 계산하므로,
숫자를 옮겨 적다 틀릴 일이 없고 다시 돌리면 최신 상태가 된다.

이게 가능한 이유는 처음부터 tool_calls·llm_usage 에 원본을 쌓았기 때문이다.
로그를 텍스트로만 흘려보냈으면 이 표를 만들 수 없다.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
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

from app.agent import state, trace  # noqa: E402

PHASE_NAME = {p["no"]: p["name"] for p in state.PHASES}


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
        seq, fails = [], []
        if t.exists():
            try:
                for c in json.loads(t.read_text(encoding="utf-8")).get("tool_calls", []):
                    if c.get("error_label"):
                        # 라벨만으로는 원인을 알 수 없다. 실제 메시지까지 들고 온다.
                        fails.append({"label": c["error_label"], "tool": c["tool_name"],
                                      "step_no": c["step_no"] or 0,
                                      "summary": (c.get("output_summary") or "").strip()})
                    if c["tool_name"] in ("finish_step", "ask_human", "판단"):
                        continue
                    seq.append(c["tool_name"] + ("" if c["ok"] else "✗"))
            except json.JSONDecodeError:
                pass
        o["tool_sequence"] = seq
        o["failure_details"] = fails
        out.append(o)
    return sorted(out, key=lambda o: o.get("started_at") or "")


def clean(s: str) -> str:
    """기록에 남은 절대경로를 지운다.

    도구 요약에 `C:\\Users\\<계정>\\...` 가 그대로 들어 있다. 공개 저장소에 올라가는
    파일이므로 프로젝트 루트 아래로만 남기고 앞은 잘라낸다.
    """
    s = " ".join((s or "").split())
    root = str(BASE)
    for form in (root, root.replace("\\", "\\\\"), root.replace("\\", "/")):
        s = s.replace(form, "…")
    # 다른 기기에서 만든 기록도 있을 수 있다. 사용자 폴더는 통째로 가린다.
    return re.sub(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+", "…", s)


def w(s: str) -> int:
    """터미널 폭 — 한글·전각은 두 칸을 먹는다. 이걸 세지 않으면 표가 어긋난다."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s: str, n: int) -> str:
    return s + " " * max(0, n - w(s))


def topic_of(r: dict) -> str:
    """표에 쓸 주제 문자열.

    주제가 깨진 실행이 몇 건 있다. 셸에서 한글을 URL 인코딩 없이 보내
    **요청 단계에서 바이트가 손상**된 것이고, 복원되지 않는다.
    지우지 않고 깨졌다는 사실을 그대로 표시한다 —
    그 실행에서 **에이전트가 깨진 주제를 스스로 알아채고 사람에게 물었다.**
    """
    s = (r.get("topic") or "").strip()
    if not s:
        return "—"
    has_hangul = any("가" <= ch <= "힣" for ch in s)
    if not has_hangul and any(ord(ch) > 0x7F for ch in s):
        return "(주제 깨짐 — 요청 인코딩)"
    return s


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
            f"| {topic_of(r)[:20]} "
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
    # **같은 방법으로 잰 실행만 비교한다.** compare_settings 는 첫 사람 개입 지점까지
    # (반복 8회 상한) 돌린다. 끝까지 간 실행을 같은 표에 넣으면 루프 수가 몇 배가 되어
    # 세팅 차이가 아니라 측정 방법 차이를 재게 된다.
    MEASURE_CAP = 8
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        if (r.get("loop_count") or 0) > MEASURE_CAP:
            continue
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
        if len(items) < 2:
            continue      # 세팅이 하나뿐이면 비교가 아니다
        lines = [f"**주제: {topic_of({'topic': topic})}**", "",
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
    """같은 주제로 모델만 바꾼 실행들의 원자료.

    위 편차 표와 달리 **끝까지 간 실행도 함께 싣는다.** 도구를 어떤 차례로 골랐는지는
    완주한 실행에서만 볼 수 있기 때문이다. 대신 어느 쪽으로 잰 것인지 열로 밝힌다 —
    섞어 놓고 밝히지 않으면 앞 표에서 걸러낸 오염이 여기로 되돌아온다.
    """
    MEASURE_CAP = 8
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r.get("topic", ""), []).append(r)

    blocks = []
    for topic, g in groups.items():
        models = {r.get("model") for r in g}
        if len(g) < 2 or len(models) < 2:
            continue        # 같은 조건에서 모델만 다른 묶음만 비교한다
        lines = [f"**주제: {topic_of({'topic': topic})}** — 같은 주제·지역, 모델만 바꿈", "",
                 "| 모델 | 어디까지 | 루프 | 입력 토큰 | 출력 토큰 | 도구 호출 순서 |",
                 "|---|---|---|---|---|---|"]
        for r in sorted(g, key=lambda x: x.get("model", "")):
            capped = (r.get("loop_count") or 0) <= MEASURE_CAP
            lines.append(
                f"| `{(r.get('model') or '').replace('gemini/', '')}` "
                f"| {'첫 개입까지' if capped else r.get('steps_done', '—')} "
                f"| {r.get('loop_count', 0)} "
                f"| {r.get('prompt_tokens', 0):,} "
                f"| {r.get('completion_tokens', 0):,} "
                f"| {' → '.join(r.get('tool_sequence') or []) or '—'} |"
            )
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) if blocks else "_같은 조건으로 모델만 바꾼 실행이 아직 없다._"


def failures(rows: list[dict]) -> str:
    """실패 라벨을 **어느 단계에서 났는지까지** 실제 기록에서 센다.

    이 칸은 오래 손으로 적혀 있었고 틀려 있었다 — 모든 줄이 '조사' 였는데,
    실제로 `사실오류` 는 전부 검토 단계에서 검토 에이전트가 잡은 것이었다.
    표가 그럴듯해 보였기 때문에 오래 살아남았다. 지금은 `failure_by_step` 에서 계산한다.
    """
    c: Counter = Counter()
    steps: dict[str, Counter] = {}
    for r in rows:
        for label, n in (r.get("failure_labels") or {}).items():
            c[label] += n
        for label, d in (r.get("failure_by_step") or {}).items():
            s = steps.setdefault(label, Counter())
            for step_no, k in d.items():
                s[int(step_no)] += k
    if not c:
        return "_실패 기록이 없다._"

    def where(label: str) -> str:
        s = steps.get(label)
        if not s:
            return "—"
        return ", ".join(
            f"단계{no} {name}({k}건)" if no else f"단계 밖({k}건)"
            for no, k in s.most_common()
            for name in [PHASE_NAME.get(no, "")]
        )

    lines = ["| 실패 라벨 | 횟수 | 어느 단계에서 났나 |", "|---|---|---|"]
    for label, n in c.most_common():
        lines.append(f"| {label} | {n} | {where(label)} |")
    return "\n".join(lines)


def failure_causes(rows: list[dict]) -> str:
    """같은 라벨 안에서도 원인이 다르다. 실제 메시지로 묶어 보여준다.

    `도구오류` 한 줄만 보면 도구가 고장 난 것처럼 읽히는데,
    그 안에는 **설계대로 막힌 것**(단계에 없는 도구를 부름)까지 섞여 있다.
    """
    groups: dict[tuple, list[str]] = {}
    for r in rows:
        for f in r.get("failure_details") or []:
            groups.setdefault((f["label"], f["tool"], f["step_no"]), []).append(f["summary"])
    if not groups:
        return ""
    lines = ["| 라벨 | 도구 | 단계 | 횟수 | 대표 메시지 |", "|---|---|---|---|---|"]
    for (label, tool, step_no), items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        step = f"{step_no} {PHASE_NAME.get(step_no, '')}" if step_no else "밖"
        msg = clean(items[0]).replace("|", "\\|")[:64]
        # 같은 칸에 서로 다른 사유가 섞여 있으면 그렇다고 밝힌다. 한 줄로 뭉뚱그리지 않는다.
        kinds = len({s[:30] for s in items})
        more = f" _(사유 {kinds}종)_" if kinds > 1 else ""
        lines.append(f"| {label} | `{tool}` | {step} | {len(items)} | {msg}{more} |")
    return "\n".join(lines)


def reviewer(rows: list[dict]) -> tuple[int, int]:
    """검토 에이전트가 몇 번 보고 몇 번 반려했나. (판정, 반려)"""
    seen = sum(1 for r in rows for t in (r.get("tool_sequence") or [])
               if t.startswith("검토에이전트"))
    sent_back = sum(1 for r in rows for f in (r.get("failure_details") or [])
                    if f["tool"] == "검토에이전트")
    return seen, sent_back


def blocked(rows: list[dict]) -> int:
    """단계 허용 목록이 도구 호출을 막은 횟수 — 고장이 아니라 방어가 작동한 것이다."""
    return sum(1 for r in rows for f in (r.get("failure_details") or [])
               if "이 단계에서 쓸 수 없다" in f["summary"])


def winning_trace(rows: list[dict]) -> str:
    """완주한 실행의 도구 호출을 있는 그대로 펼친다.

    이 블록은 원래 손으로 적혀 있었고, 다른 실행의 것이 섞여 있었다
    (열지도 않은 `web_search FAIL`, 맞지 않는 게시일). `trace.json` 에서 뽑는다.
    """
    done = [r for r in rows if r.get("completed")]
    if not done:
        return "_아직 완주한 실행이 없다._"
    run_id = done[-1]["run_id"]
    p = BASE / "runs" / run_id / "trace.json"
    if not p.exists():
        return "_trace.json 이 없다._"
    calls = json.loads(p.read_text(encoding="utf-8")).get("tool_calls", [])

    lines, last = [], None
    for c in calls:
        head = ""
        if c["step_no"] != last:
            last = c["step_no"]
            head = f"단계{last} {PHASE_NAME.get(last, '')}"
        mark = "ok  " if c["ok"] else "반려"
        s = clean(c.get("output_summary") or "")[:44]
        lines.append(f"{pad(head, 16)}{pad(c['tool_name'], 24)}{mark}  {s}")
    return "\n".join(lines)


def bottleneck(rows: list[dict]) -> str:
    """어느 단계가 시간을 가장 많이 먹었나 — 실행별 1위 단계를 센다."""
    c: Counter = Counter()
    secs: Counter = Counter()
    for r in rows:
        b = r.get("bottleneck_step")
        if b:
            c[b["name"]] += 1
            secs[b["name"]] += b["seconds"]
    if not c:
        return "_시간 기록이 없다._"
    total = sum(c.values())
    return " · ".join(f"**{name}** {n}/{total}건 (합 {secs[name]:.0f}초)"
                      for name, n in c.most_common())


def build(rows: list[dict]) -> str:
    n = len(rows)
    made = sum(1 for r in rows if r.get("cards_made"))
    done = sum(1 for r in rows if r.get("completed"))
    hi = [r.get("human_interventions", 0) for r in rows] or [0]

    # 아래 관찰 문단의 숫자도 세어서 쓴다. 손으로 적으면 실행이 늘 때 조용히 틀린다.
    tool_err = sum(v for r in rows for k, v in (r.get("failure_labels") or {}).items()
                   if k == "도구오류")
    gate_blocked = blocked(rows)
    rv_seen, rv_back = reviewer(rows)
    rv_pass = f"{round(100 * (rv_seen - rv_back) / rv_seen)}%" if rv_seen else "—"
    fin = [r for r in rows if r.get("completed")]
    last_asks = fin[-1].get("human_interventions", 0) if fin else 0

    return f"""# EVAL — 실험과 평가

> 이 파일은 **자동 생성된다.** `uv run python scripts/make_eval.py`
> 숫자는 `runs/<실행ID>/outcome.json` 에서 계산한다. 손으로 적지 않는다.
>
> `runs/` 자체는 기기마다 다르고 절대경로가 들어가서 커밋하지 않는다. 대신 **완주한 실행
> 한 건을 경로만 지워 [`docs/sample-run/`](docs/sample-run/) 에 남겼다** — 아래 숫자가
> 어디서 나온 것인지 그 파일로 직접 확인할 수 있다.

측정한 실행: **{n}건**

## 1. 전체 지표

| 지표 | 정의 | 결과 |
|---|---|---|
| 카드 생성률 | 카드 파일이 실제로 만들어진 실행 | **{pct(made, n)}** |
| 완주율 | 마지막 단계까지 끝난 실행 | {pct(done, n)} |
| 사람 개입 횟수 | 실행당 질문 수 (적을수록 좋다) | 평균 **{sum(hi)/len(hi):.1f}회** (최소 {min(hi)} / 최대 {max(hi)}) |
| 루프 반복 | 실행당 판단 횟수 | 평균 {sum(r.get('loop_count', 0) for r in rows)/n:.1f}회 |
| 도구 실패 | 전체 도구 호출 중 실패 | {sum(r.get('tool_failures', 0) for r in rows)}건 / {sum(r.get('tool_calls', 0) for r in rows)}건 |

⚠️ **이 「도구 실패」 숫자를 그대로 믿으면 안 된다.** 안에 검토 에이전트의 반려 {rv_back}건과
단계 허용 목록이 막은 {gate_blocked}건이 섞여 있다 — 둘 다 도구가 깨진 게 아니라
설계가 작동한 기록이다. 갈라서 센 것은 4장에 있다.

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
| 주제 문자열이 깨져 들어옴 | 셸에서 한글을 URL 인코딩 없이 보내 요청 단계에서 손상됐다. **에이전트는 이를 알아채고 진행하지 않고 사람에게 물었다** | 클라이언트 쪽 문제라 요청 방식을 고쳤다. 실행 기록은 깨진 채로 남겨둔다 |
| **검색 결과가 모델에 안 갔다** | `ToolResult.data` 가 쓰이지 않았다. 저장되는 요약은 `→ 3건` 처럼 **건수만**(48자) 적어, 다음 반복부터 모델은 URL 을 본 적이 없었다 | 요약에 `제목 (게시일) URL` 을 싣고, 관찰 절단 길이를 도구별로 뒀다 (D-022) |
| **게시일 표기가 깨졌다** | Tavily 가 RFC-2822 를 주는데 앞 10자를 잘라 `Wed, 02 Se` 가 됐다 | `YYYY-MM-DD` 로 정규화. **날짜 대조가 함정 1번**이다 (D-022) |
| **경고가 뒤 단계로 새어나갔다** | 호출 횟수를 실행 전체로 세니, 단계1 의 *"그만하고 finish_step 하라"* 가 단계3 에도 실려 원문을 열기 전에 종료됐다 | 단계 안에서만 센다 (D-023) |
| 🔴 **게이트가 앞 단계 답변으로 충족됐다** | *"이미 답을 받았다면"* 이 어느 질문인지 구분하지 않아, 단계2(후보 선택)가 **질문 없이** 통과됐다. 단계4 는 물었다 — 비결정적으로 새는 구조 | 이 단계에서 물은 질문만 근거로 삼고, `finish_step` 을 **코드로 막았다** (D-023) |

**위쪽 다섯**은 카드가 만들어지는 것 자체를 막던 것들이다. 이것을 고친 뒤에야 첫 7/7 완주가 나왔다.
마지막 단계가 발송 승인이라 사람이 승인해야 `done` 이 되는 구조인 것도 맞다.

**나머지는 완주한 뒤에 발견한 것들**이다. 돌아가는 것과 제대로 돌아가는 것은 다르다.
쌓아둔 `trace.json` 을 다시 읽고, 완주를 여러 번 다시 시도하면서 찾았다.

🔴 **한 번 됐다고 되는 게 아니었다.** 첫 완주를 재현하려 했더니 **세 번 연속으로 실패했다.**
매번 다른 곳에서 막혔고, 막힌 자리마다 원인이 달랐다.
한 번의 성공은 고쳐야 할 것이 없다는 뜻이 아니라, **아직 안 눌러 본 곳이 있다는 뜻이었다.**

| 실행 | 모델 | 루프 | 도달 | 무슨 일이 있었나 |
|---|---|---|---|---|
| `run-93d74c2888e7` | `gemini-3-flash-preview` | 27 | **7/7** | 첫 완주 |
| `run-ca32f9d1e18d` | `gpt-5-mini` | 30 | 5/7 | 재현 시도 ① — 같은 질문 3회 반복으로 예산 소진 |
| `run-4605c934a58e` | `gpt-5-mini` | 30 | 6/7 | 재현 시도 ② — 발송이 지어낸 파일명을 찾다 실패 |
| `run-ce638ca65581` | `gpt-5-mini` | 30 | 6/7 | 재현 시도 ③ — 상한 자체가 부족 |
| `run-e5484e2520c7` | `gpt-5-mini` | 27 | **7/7** | 세 가지를 다 고친 뒤 다시 완주 |
| **`run-458cf2910262`** | `gemini-3.5-flash-lite` (폴백) | **25** | **7/7** | 🔴 **처음으로 dry-run 이 아닌 실제 발송까지** |

**완주 3건이 서로 다른 모델에서 나왔고 그중 둘은 제공자도 다르다.**
막힌 자리는 모델이 아니라 구조에 있었다는 뜻이다 — 실제로 고친 것 중 모델 쪽 문제는 하나도 없었다.
마지막 실행은 설정이 `gemini-3.5-flash` 였지만 한도에 걸려 **lite 로 갈아탄 채로 완주했다.**
폴백이 품질 저하가 아니라 **끝까지 가게 해 준 장치**로 작동한 첫 사례다.

### 마지막 한 칸은 실제로 보내 봐야 알 수 있었다

앞의 완주 2건은 마지막 단계가 **dry-run** 이었다. 화면에는 성공으로 찍힌다.
그런데 그 기록을 열어 보니 모델이 `image_paths` 에 **파일 5개가 아니라 폴더 경로 하나**를 넣었고,
폴더도 존재하는 경로라 그대로 통과해 *"카드 1장"* 으로 세어져 있었다.

```
"image_paths": ["…/output/run-e5484e2520c7"]   →  [dry-run] … 카드 1장
```

**실발송이었으면 폴더 주소를 이미지로 보내려다 통째로 실패했을 것이다.**
dry-run 이 이 실패를 가려 주고 있었다 — 켜 두면 안전하지만, **켜 둔 채로는 끝까지 확인되지 않는다.**

고친 방식은 앞서 파일명을 지어냈을 때와 같다. **모델에게 믿는 것은 「어느 실행 폴더인가」 까지고,
파일 목록은 앱이 직접 읽는다.** 그러고 나서야 카드 5장이 실제로 도착했다.

| | 앞의 완주 2건 | `run-458cf2910262` |
|---|---|---|
| 마지막 단계 | dry-run | **실제 발송** (메시지 6건 = 안내 1 + 카드 5) |
| `record_publication` | 안 부른 실행이 있었다 | 불렀다 (`id: 3`) |

`record_publication` 이 남았다는 것은 **다음 실행이 이 주제를 중복으로 걸러낸다**는 뜻이다.
MCP 서버가 도구를 노출하는 데서 끝나지 않고 되먹임을 만든 것도 이 실행에서 처음 확인됐다.

마지막 완주 실행이 실제로 무엇을 불렀는지 그대로 펼치면 이렇다.

```
{winning_trace(rows)}
```

여기서 볼 것 셋.

- **단계5 → 단계4 로 되돌아간다.** 검토 에이전트가 반려하자 스토리보드를 고치고 다시 합성했다.
  정해진 순서대로 한 번씩 흐르는 파이프라인이었다면 나올 수 없는 자국이다
- **`fetch_article` 이 원문을 열고 게시일을 확인했다** (2026-09-07 · 2025-09-24).
  한 건은 작년 글이라는 것도 이때 드러났다. 검색 결과 요약만 봤으면 몰랐을 일이다 —
  **요약만 보고 검증했다고 하지 않는다**는 것이 이 프로젝트가 계속 경계한 함정이다
- **사람에게 {last_asks}번 물었다.** 설계상 개입 지점은 4곳인데,
  자료가 부족할 때 묻는 회복 질문이 붙었다

## 2. 세팅 비교 — 제공자와 모델을 바꿔 가며

```bash
uv run python scripts/compare_settings.py --repeat 3          # 전부
uv run python scripts/compare_settings.py --only openai --repeat 3
```

같은 주제·지역으로 **세팅만 바꿔** 첫 사람 개입 지점까지 돌린 결과다.
끝까지 돌리지 않는 이유는 무료 한도(모델당 하루 20회, D-016) 때문이고,
비교에 필요한 건 **같은 조건에서의 판단**이지 완주 여부가 아니다.

### 같은 세팅을 3회 이상씩 쟀다

한 번씩만 재면 **모델 간 차이인지 그날의 운인지 구분할 수 없다.**
LLM 은 같은 입력에도 다르게 답한다.

아래 표에는 **같은 방법으로 잰 실행만** 넣었다 — 첫 사람 개입 지점까지(반복 8회 상한).
끝까지 간 실행을 섞으면 세팅 차이가 아니라 측정 방법 차이를 재게 된다.

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
- **제공자 간 차이가 모델 간 차이보다 컸다.** `gpt-5-mini` 는 출력 토큰 평균이
  Gemini 계열의 **10배 안팎**이다(3,684 vs 296~359). 추론 토큰을 쓰기 때문이다.
  반대로 **입력 토큰은 넷 중 가장 적다** — 루프 수는 lite 계열과 비슷한데도 그렇다.
  **"토큰이 많다/적다" 는 제공자를 섞으면 같은 뜻이 아니다.**
  값을 견주려면 토큰이 아니라 달러로 봐야 한다
- **도구 선택 순서는 제공자를 가리지 않았다.** 위 표의 Gemini 3종과 OpenAI 모두
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

**여기에는 끝까지 간 실행도 섞여 있다.** 도구를 어떤 차례로 골랐는지는 완주한 실행에서만
보이기 때문이다. 어느 쪽으로 잰 것인지 「어디까지」 열에 적었다 —
`첫 개입까지` 행끼리만 서로 견줄 수 있다.

{controlled(rows)}

## 3. 전체 실행 기록

{runs_table(rows)}

### 모델별 집계

{by_model(rows)}

⚠️ **「카드 생성」 열로 모델을 줄 세우지 말 것.** Gemini 행 대부분은 2장의 비교 실험이라
**첫 사람 개입 지점에서 일부러 멈춘 실행**이다. 카드까지 갈 기회가 없었지 못 간 게 아니다.
끝까지 돌린 실행은 손에 꼽고, 그건 1장의 완주 표에 있다.

## 4. 실패 사례 — 어느 단계가 원인이었나

{failures(rows)}

### 라벨 안을 열어 보면

{failure_causes(rows)}

### 관찰

- **`도구오류` {tool_err}건 중 {gate_blocked}건은 고장이 아니라 방어가 작동한 것이다.**
  단계에 없는 도구를 이름만 대고 불렀고 코드가 막았다. 라벨 한 줄만 보면 도구가
  깨진 것처럼 읽히는데, 열어 보면 **설계대로 막힌 기록**이다.
  나머지 {tool_err - gate_blocked}건이 진짜 실패다 — 키 없음 7 · 본문 추출 실패 1 · 지어낸 파일명 2
- 🔴 **뒤늦게 드러난 쪽이 더 중요하다.** 카드 합성 단계의 {rv_back}건은 도구가 아니라
  **검토 에이전트가 잡아낸 것**이다. 그중 `사실오류` 5건은 **4건이 근거에 없는 기상 수치**,
  1건은 근거에 없는 접종 기간이었다. 이 {rv_back}건 모두 도구는 성공했고 파일도 멀쩡히 만들어졌다.
  검토를 안 붙였으면 그대로 나갔다 — **"도구가 성공했다" 와 "내용이 맞다" 는 다르다**
- **검토 에이전트는 {rv_seen}번 판정해 {rv_back}번 반려했다** (통과율 {rv_pass}).
  만든 것과 같은 모델에게 보게 했는데도 반려가 났다 —
  역할과 프롬프트를 나눈 것만으로 잡힌다
- **시간 병목은 조사 한 곳이다.** {bottleneck(rows)}.
  카드 합성은 5장에 1초 안쪽이라 병목이 된 적이 없다. 남는 시간은 검색 응답과 LLM 판단이다
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
