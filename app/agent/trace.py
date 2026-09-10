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
