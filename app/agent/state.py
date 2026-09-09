"""실행 상태 저장·복원 (루브릭 3번 "중간에 끊겨도 이어서 진행").

정본은 SQLite 다. 프로세스가 죽어도 여기 남아 있으면 이어갈 수 있다.

질문 중복 제출은 `UNIQUE (run_id, question_id, version)` 한 줄로 막는다.
같은 답을 두 번 보내도 두 번 실행되지 않는다 (PRD 5장).
"""

from __future__ import annotations

import json
import uuid
from contextlib import closing
from dataclasses import dataclass
from typing import Any

from app.db import connect
from app.llm.budget import utc_now

# 워크플로 단계 (PRD 3장). 사람이 개입하는 곳은 gate=True.
PHASES: list[dict[str, Any]] = [
    {"no": 1, "name": "조사", "gate": False,
     "goal": ("주제에 맞는 최근 소식 후보를 모은다. 날씨가 필요하면 함께 조회한다. "
              "**후보를 고르기 전에 list_past_publications 로 과거 발행 이력을 확인해** "
              "최근에 이미 다룬 주제는 후순위로 내린다."),
     "tools": ["web_search", "get_weather", "list_past_publications"]},
    {"no": 2, "name": "후보 선택", "gate": True,
     "goal": "모은 후보 중 카드뉴스에 실을 소식을 사람이 1~3개 고른다.",
     "tools": []},
    {"no": 3, "name": "심층 검증", "gate": False,
     "goal": "고른 소식의 원문을 열어 날짜·수치를 대조한다. 확인된 사실 / 발표자 주장 / 미확인 으로 나눈다.",
     "tools": ["fetch_article", "get_weather"]},
    {"no": 4, "name": "스토리보드", "gate": True,
     "goal": ("카드 5장의 제목·본문·자세를 계획하고 사람의 승인을 받는다. "
              "계획을 세우기 전에 get_audience_profile 과 get_card_template 으로 "
              "글쓰기 규칙과 카드 양식을 확인한다."),
     "tools": ["get_audience_profile", "get_card_template"]},
    {"no": 5, "name": "카드 합성", "gate": False,
     "goal": "승인된 스토리보드로 카드 이미지를 만든다.",
     "tools": ["compose_cards"]},
    {"no": 6, "name": "검수", "gate": True,
     "goal": "완성된 카드를 사람이 보고 승인하거나 수정을 지시한다.",
     "tools": []},
    {"no": 7, "name": "발송", "gate": True,
     "goal": ("사람이 발송을 승인하면 보낸다. 기본은 보내지 않는다(dry-run). "
              "발송 처리 뒤에는 record_publication 으로 발행 이력을 남겨 "
              "다음 실행이 같은 주제를 반복하지 않게 한다."),
     "tools": ["send_line", "record_publication"]},
]

PHASE_BY_NO = {p["no"]: p for p in PHASES}


@dataclass
class Run:
    run_id: str
    topic: str
    region: str
    status: str
    provider: str
    model: str
    loop_count: int
    image_calls: int
    active_ms: int
    stop_reason: str | None
    started_at: str
    ended_at: str | None


def _row_to_run(r) -> Run:
    keys = r.keys()
    return Run(
        run_id=r["run_id"], topic=r["topic"], region=r["region"] or "",
        status=r["status"], provider=r["provider"] or "", model=r["model"] or "",
        loop_count=r["loop_count"], image_calls=r["image_calls"],
        active_ms=(r["active_ms"] if "active_ms" in keys else 0),
        stop_reason=r["stop_reason"], started_at=r["started_at"], ended_at=r["ended_at"],
    )


def add_active_ms(run_id: str, ms: int) -> int:
    """에이전트가 실제로 일한 시간만 더한다. 사람을 기다린 시간은 빼고 센다."""
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE runs SET active_ms = active_ms + ? WHERE run_id = ?",
                     (max(0, int(ms)), run_id))
        r = conn.execute("SELECT active_ms FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return r["active_ms"]


# ── 실행 ────────────────────────────────────────────────────
def create_run(topic: str, region: str, provider: str, model: str) -> str:
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    with closing(connect()) as conn, conn:
        conn.execute(
            "INSERT INTO runs (run_id, topic, region, status, provider, model, started_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (run_id, topic, region, "running", provider, model, utc_now()),
        )
        for p in PHASES:
            conn.execute(
                "INSERT INTO steps (run_id, step_no, name, status) VALUES (?,?,?,?)",
                (run_id, p["no"], p["name"], "pending"),
            )
    return run_id


def get_run(run_id: str) -> Run | None:
    with closing(connect()) as conn:
        r = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return _row_to_run(r) if r else None


def list_runs(limit: int = 30) -> list[Run]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_run(r) for r in rows]


def set_status(run_id: str, status: str, stop_reason: str | None = None) -> None:
    ended = utc_now() if status in ("done", "failed", "stopped") else None
    with closing(connect()) as conn, conn:
        conn.execute(
            "UPDATE runs SET status = ?, stop_reason = COALESCE(?, stop_reason), "
            "ended_at = COALESCE(?, ended_at) WHERE run_id = ?",
            (status, stop_reason, ended, run_id),
        )


def clear_stop_reason(run_id: str) -> None:
    """다시 이어서 진행할 때 지난 중단 사유를 지운다. 안 지우면 화면에 계속 남는다."""
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE runs SET stop_reason = NULL, ended_at = NULL WHERE run_id = ?",
                     (run_id,))


def bump_loop(run_id: str) -> int:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE runs SET loop_count = loop_count + 1 WHERE run_id = ?", (run_id,))
        r = conn.execute("SELECT loop_count FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return r["loop_count"]


# ── 단계 ────────────────────────────────────────────────────
def current_step(run_id: str) -> dict | None:
    """아직 끝나지 않은 가장 앞선 단계."""
    with closing(connect()) as conn:
        r = conn.execute(
            "SELECT * FROM steps WHERE run_id = ? AND status NOT IN ('done','skipped') "
            "ORDER BY step_no LIMIT 1", (run_id,)
        ).fetchone()
    if not r:
        return None
    return {"step_no": r["step_no"], "name": r["name"], "status": r["status"],
            "retry_count": r["retry_count"]}


def start_step(run_id: str, step_no: int) -> None:
    with closing(connect()) as conn, conn:
        conn.execute(
            "UPDATE steps SET status='running', started_at=COALESCE(started_at, ?) "
            "WHERE run_id=? AND step_no=?", (utc_now(), run_id, step_no))


def finish_step(run_id: str, step_no: int, status: str = "done") -> None:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE steps SET status=?, ended_at=? WHERE run_id=? AND step_no=?",
                     (status, utc_now(), run_id, step_no))


def bump_retry(run_id: str, step_no: int) -> int:
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE steps SET retry_count = retry_count + 1 "
                     "WHERE run_id=? AND step_no=?", (run_id, step_no))
        r = conn.execute("SELECT retry_count FROM steps WHERE run_id=? AND step_no=?",
                         (run_id, step_no)).fetchone()
    return r["retry_count"]


def steps_of(run_id: str) -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM steps WHERE run_id=? ORDER BY step_no", (run_id,)).fetchall()
    return [dict(r) for r in rows]


# ── 질문 (사람 개입 지점) ───────────────────────────────────
def ask(run_id: str, question_id: str, payload: dict) -> int:
    """질문을 저장하고 실행을 대기 상태로 바꾼다.

    같은 question_id 를 다시 물으면 version 이 올라간다.
    """
    with closing(connect()) as conn, conn:
        r = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM questions "
            "WHERE run_id=? AND question_id=?", (run_id, question_id)).fetchone()
        version = r["v"] + 1
        conn.execute(
            "INSERT INTO questions (run_id, question_id, version, payload_json, asked_at) "
            "VALUES (?,?,?,?,?)",
            (run_id, question_id, version, json.dumps(payload, ensure_ascii=False), utc_now()),
        )
        conn.execute("UPDATE runs SET status='waiting_for_user' WHERE run_id=?", (run_id,))
    return version


def open_question(run_id: str) -> dict | None:
    """아직 답이 안 온 질문. 새로고침해도 같은 질문이 나오는 근거."""
    with closing(connect()) as conn:
        r = conn.execute(
            "SELECT * FROM questions WHERE run_id=? AND answered_at IS NULL "
            "ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()
    if not r:
        return None
    return {"question_id": r["question_id"], "version": r["version"],
            **json.loads(r["payload_json"])}


class StaleAnswer(Exception):
    """지난 질문에 뒤늦게 온 답. 새 작업을 시작하지 않는다."""


def answer(run_id: str, question_id: str, version: int, value: Any) -> None:
    """답을 저장한다. 이미 답이 있으면 조용히 무시한다 (중복 제출 차단)."""
    with closing(connect()) as conn, conn:
        r = conn.execute(
            "SELECT id, answered_at FROM questions "
            "WHERE run_id=? AND question_id=? AND version=?",
            (run_id, question_id, version)).fetchone()
        if r is None:
            raise StaleAnswer("지난 질문입니다. 새 작업을 시작하지 않습니다.")
        if r["answered_at"] is not None:
            return                      # 두 번째 제출 — 한 번만 실행한다
        conn.execute("UPDATE questions SET answer_json=?, answered_at=? WHERE id=?",
                     (json.dumps(value, ensure_ascii=False), utc_now(), r["id"]))
        conn.execute("UPDATE runs SET status='running' WHERE run_id=?", (run_id,))


def answers_of(run_id: str) -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT question_id, version, payload_json, answer_json, answered_at "
            "FROM questions WHERE run_id=? AND answered_at IS NOT NULL ORDER BY id",
            (run_id,)).fetchall()
    out = []
    for r in rows:
        out.append({
            "question_id": r["question_id"],
            "version": r["version"],
            "question": json.loads(r["payload_json"]).get("question", ""),
            "answer": json.loads(r["answer_json"]) if r["answer_json"] else None,
        })
    return out


def usage_of(run_id: str) -> dict:
    """이 실행이 쓴 토큰·비용·시간. 화면 하단과 대시보드가 쓴다."""
    with closing(connect()) as conn:
        u = conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(prompt_tokens),0) AS pin, "
            "COALESCE(SUM(completion_tokens),0) AS pout, COALESCE(SUM(usd),0) AS usd "
            "FROM llm_usage WHERE run_id = ?", (run_id,)).fetchone()
        t = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(duration_ms),0) AS ms, "
            "COALESCE(SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END),0) AS fails "
            "FROM tool_calls WHERE run_id = ?", (run_id,)).fetchone()
    return {"llm_calls": u["calls"], "prompt_tokens": u["pin"],
            "completion_tokens": u["pout"], "usd": round(float(u["usd"]), 6),
            "tool_calls": t["n"], "tool_ms": t["ms"], "tool_fails": t["fails"]}


def step_timing(run_id: str) -> list[dict]:
    """단계별 소요시간·도구 호출 수. '어느 단계가 병목인지' 를 보려면 이게 필요하다."""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT s.step_no, s.name, s.status, s.retry_count, "
            "  COALESCE(SUM(t.duration_ms), 0) AS tool_ms, COUNT(t.id) AS calls "
            "FROM steps s LEFT JOIN tool_calls t "
            "  ON t.run_id = s.run_id AND t.step_no = s.step_no "
            "WHERE s.run_id = ? GROUP BY s.step_no ORDER BY s.step_no", (run_id,)).fetchall()
    return [dict(r) for r in rows]


def logs_after(run_id: str, after_id: int = 0, limit: int = 200) -> list[dict]:
    """실행 로그를 id 이후로 가져온다. 화면 패널이 이어받는 근거."""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT id, step_no, tool_name, reason, output_summary, ok, error_label, "
            "duration_ms, created_at FROM tool_calls "
            "WHERE run_id = ? AND id > ? ORDER BY id LIMIT ?",
            (run_id, after_id, limit)).fetchall()
    return [dict(r) for r in rows]


def observations(run_id: str, limit: int = 40) -> list[dict]:
    """지금까지의 도구 호출 결과. 루프가 '관찰'로 삼는 재료."""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT step_no, tool_name, reason, output_summary, ok, error_label, duration_ms "
            "FROM tool_calls WHERE run_id=? ORDER BY id LIMIT ?", (run_id, limit)).fetchall()
    return [dict(r) for r in rows]
