"""실행 기록 내보내기 — `runs/<실행ID>/trace.json` · `outcome.json` (⭐확장1).

**이건 나중에 붙일 수 없다.** 로그를 텍스트로만 흘려보내면 평가 표를 만들 수 없다.
그래서 원본을 처음부터 `tool_calls` · `llm_usage` 테이블에 쌓아 왔고, 여기서는 꺼내 쓰기만 한다.

  trace.json    도구 호출 순서, 입출력 요약, 판단 근거, 소요시간, 토큰
  outcome.json  완주 여부, 사람 개입 횟수, 실패 라벨, 단계별 병목

이 두 파일이 쌓이면 EVAL 표와 비용 대시보드가 스크립트로 자동 생성된다.
"""

from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
from typing import Any

from app.agent import state
from app.config import get_settings
from app.db import connect


def _run_dir(run_id: str) -> Path:
    d = get_settings().runs_path / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_trace(run_id: str) -> dict[str, Any]:
    run = state.get_run(run_id)
    if run is None:
        raise ValueError(f"없는 실행: {run_id}")

    with closing(connect()) as conn:
        calls = [dict(r) for r in conn.execute(
            "SELECT id, step_no, tool_name, reason, input_json, output_summary, ok, "
            "error_label, duration_ms, created_at FROM tool_calls "
            "WHERE run_id = ? ORDER BY id", (run_id,))]
        usage = [dict(r) for r in conn.execute(
            "SELECT provider, model, prompt_tokens, completion_tokens, usd, created_at "
            "FROM llm_usage WHERE run_id = ? ORDER BY id", (run_id,))]

    return {
        "run_id": run.run_id,
        "topic": run.topic,
        "region": run.region,
        "provider": run.provider,
        "model": run.model,
        "status": run.status,
        "stop_reason": run.stop_reason,
        "loop_count": run.loop_count,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "steps": state.step_timing(run_id),
        "questions": state.answers_of(run_id),
        "tool_calls": calls,
        "llm_usage": usage,
        "totals": state.usage_of(run_id),
    }


def build_outcome(run_id: str) -> dict[str, Any]:
    """무엇이 잘됐고 어디서 막혔나. 평가 표의 한 줄이 된다."""
    trace = build_trace(run_id)
    calls = trace["tool_calls"]

    # 라벨만 세면 "어느 단계에서 났나" 를 나중에 복원할 수 없다.
    # 실제로 EVAL 표가 그 칸을 손으로 적어두고 오래 틀린 채로 있었다. 단계까지 함께 센다.
    labels: dict[str, int] = {}
    by_step: dict[str, dict[str, int]] = {}
    for c in calls:
        if c["error_label"]:
            labels[c["error_label"]] = labels.get(c["error_label"], 0) + 1
            # 단계 밖(도구 준비·종료 처리)에서 난 것은 step_no 가 없다. 0 으로 모은다.
            k = str(c["step_no"] or 0)
            d = by_step.setdefault(c["error_label"], {})
            d[k] = d.get(k, 0) + 1

    steps = trace["steps"]
    done_steps = [s for s in steps if s["status"] == "done"]
    bottleneck = max(steps, key=lambda s: s["tool_ms"] or 0, default=None)

    compose = [c for c in calls if c["tool_name"] == "compose_cards" and c["ok"]]

    # 실제로 응답한 모델을 센다. 한도에 걸려 폴백되면 설정값과 달라진다 (D-016).
    used: dict[str, int] = {}
    for u in trace["llm_usage"]:
        used[u["model"]] = used.get(u["model"], 0) + 1
    primary = max(used, key=used.get) if used else trace["model"]

    return {
        "run_id": run_id,
        "topic": trace["topic"],
        "configured_model": f"{trace['provider']}/{trace['model']}",
        "model": f"{trace['provider']}/{primary}",   # 가장 많이 응답한 모델
        "models_used": used,
        # 완주 = 마지막 단계까지 끝났는가
        "completed": trace["status"] == "done",
        "status": trace["status"],
        "stop_reason": trace["stop_reason"],
        "steps_done": f"{len(done_steps)}/{len(steps)}",
        # 사람 개입 횟수 — 적을수록 좋다 (PRD 7장 지표)
        "human_interventions": len(trace["questions"]),
        "cards_made": bool(compose),
        "regenerations": max(0, len(compose) - 1),
        "loop_count": trace["loop_count"],
        "tool_calls": trace["totals"]["tool_calls"],
        "tool_failures": trace["totals"]["tool_fails"],
        "failure_labels": labels,
        "failure_by_step": by_step,          # {라벨: {단계번호: 횟수}}, 0 = 단계 밖
        "llm_calls": trace["totals"]["llm_calls"],
        "prompt_tokens": trace["totals"]["prompt_tokens"],
        "completion_tokens": trace["totals"]["completion_tokens"],
        "usd": trace["totals"]["usd"],
        "tool_seconds": round((trace["totals"]["tool_ms"] or 0) / 1000, 1),
        "bottleneck_step": (
            {"step_no": bottleneck["step_no"], "name": bottleneck["name"],
             "seconds": round((bottleneck["tool_ms"] or 0) / 1000, 1)}
            if bottleneck and bottleneck["tool_ms"] else None
        ),
        "started_at": trace["started_at"],
        "ended_at": trace["ended_at"],
    }


def build_sources(run_id: str) -> str:
    """ZIP 에 함께 넣는 출처 기록(`sources.md`).

    **앱이 trace 에서 직접 읽어 만든다. 모델에게 목록을 만들게 하지 않는다.**
    이 프로젝트는 모델이 파일명을 지어내고 폴더 경로를 파일이라고 넘긴 것을
    두 번 겪었다(D-025). 출처는 그런 실수가 나면 안 되는 자리다.

    근거는 두 군데서 온다.
      URL          `fetch_article` 의 입력
      제목·게시일   그 호출의 결과 요약
    """
    import re

    trace = build_trace(run_id)
    calls = trace["tool_calls"]

    def _kst(s: str | None) -> str:
        from app.timefmt import to_kst
        return to_kst(s, "%Y-%m-%d %H:%M")

    # 설정한 모델과 실제로 답한 모델이 다를 수 있다 — 무료 한도에 걸리면 폴백된다.
    # 출처 기록에서 이걸 뭉뚱그리면 "그 모델로 돌았다" 고 잘못 읽힌다.
    def _models(tr: dict) -> str:
        used: dict[str, int] = {}
        for u in tr["llm_usage"]:
            used[u["model"]] = used.get(u["model"], 0) + 1
        conf = f"{tr['provider']}/{tr['model']}"
        if not used:
            return f"`{conf}` (설정값)"
        actual = max(used, key=used.get)
        if actual == tr["model"]:
            return f"`{conf}`"
        return f"`{tr['provider']}/{actual}` — 설정은 `{conf}` 였으나 한도로 폴백됨"

    L = [f"# 출처 기록 — {trace['topic'] or '(주제 없음)'}", ""]
    L += [
        f"- 실행 ID: `{run_id}`",
        f"- 대상 지역: {trace['region'] or '—'}",
        f"- **조사 기준일: {_kst(trace['started_at'])} (KST)** — 이 시각 기준으로 자료를 모았다",
        f"- 사용 모델: {_models(trace)}",
        "",
        "이 파일은 **앱이 실행 기록에서 직접 생성**했다. 모델이 쓴 목록이 아니다.",
        "",
    ]

    # ── 원문을 직접 열어 확인한 것 ──────────────────────────
    opened = [c for c in calls if c["tool_name"] == "fetch_article" and c["ok"]]
    L += ["## 원문을 직접 열어 확인한 자료", ""]
    if opened:
        L += ["| # | 제목 | 게시일 | URL |", "|---|---|---|---|"]
        for i, c in enumerate(opened, 1):
            try:
                url = json.loads(c["input_json"] or "{}").get("url", "")
            except json.JSONDecodeError:
                url = ""
            s = c["output_summary"] or ""
            title = (re.search(r"원문 확인: '(.*?)'", s) or [None, "—"])[1]
            day = (re.search(r"게시일=(\S+)", s) or [None, "—"])[1]
            L.append(f"| {i} | {title.replace('|', '｜')} | {day} | {url} |")
    else:
        L.append("_원문을 연 기록이 없다._")
    L.append("")

    # ── 검색으로 훑은 범위 ─────────────────────────────────
    searched = [c for c in calls if c["tool_name"] == "web_search" and c["ok"]]
    L += ["## 검색으로 훑은 범위", ""]
    if searched:
        L += ["| 검색어 | 기간 | 결과 |", "|---|---|---|"]
        for c in searched:
            try:
                inp = json.loads(c["input_json"] or "{}")
            except json.JSONDecodeError:
                inp = {}
            days = inp.get("days")
            n = (re.search(r"→ (\d+)건", c["output_summary"] or "") or [None, "—"])[1]
            L.append(f"| {str(inp.get('query', '—')).replace('|', '｜')} "
                     f"| {f'최근 {days}일' if days else '제한 없음'} | {n}건 |")
    else:
        L.append("_검색 기록이 없다._")
    L.append("")

    # ── 날씨 ───────────────────────────────────────────────
    weather = [c for c in calls if c["tool_name"] == "get_weather" and c["ok"]]
    if weather:
        L += ["## 날씨", "",
              f"{weather[0]['output_summary']}", "",
              "출처: Open-Meteo (`timezone=Asia/Seoul` 로 조회해 한국 날짜로 받는다)", ""]

    # ── 카드 순서 ──────────────────────────────────────────
    out = get_settings().output_path / run_id
    cards = sorted(out.glob("card_*.png")) if out.exists() else []
    L += ["## 카드 순서", ""]
    L += [f"{i}. `{p.name}`" for i, p in enumerate(cards, 1)] or ["_카드 파일이 없다._"]
    L += ["", "파일명을 이름순으로 정렬하면 카드 순서와 같다.", ""]

    L += ["---", "",
          "**카드별로 어느 자료를 썼는지는 기록하지 않는다.** 지금 구조에서는 "
          "스토리보드가 자료를 묶어서 참고하므로, 카드 하나에 출처 하나를 "
          "갖다 붙이면 실제보다 정확해 보이게 된다. "
          "무엇을 언제까지 조사했는지와 어떤 원문을 열었는지까지만 남긴다.", ""]
    return "\n".join(L)


def export(run_id: str) -> dict[str, str]:
    """두 파일을 쓰고 경로를 돌려준다."""
    d = _run_dir(run_id)
    t, o = d / "trace.json", d / "outcome.json"
    t.write_text(json.dumps(build_trace(run_id), ensure_ascii=False, indent=2), encoding="utf-8")
    o.write_text(json.dumps(build_outcome(run_id), ensure_ascii=False, indent=2), encoding="utf-8")
    return {"trace": str(t), "outcome": str(o)}


def export_all() -> list[str]:
    """지금까지의 모든 실행을 내보낸다. EVAL 표를 만들기 전에 한 번 돌린다."""
    made = []
    for run in state.list_runs(limit=200):
        try:
            export(run.run_id)
            made.append(run.run_id)
        except Exception:  # noqa: BLE001 - 한 건이 깨져도 나머지는 뽑는다
            continue
    return made
