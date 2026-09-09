"""호출 수·비용 상한 (PRD 3장 종료 조건).

어댑터가 LLM 으로 가는 **유일한 관문**이라 여기서 막는다.
루프가 아무리 돌아도 이 문을 못 지나가면 더 못 나간다.

  Gemini  무료 티어라 과금은 없다 → 호출 수로 막는다 (1회 40 / 하루 300)
  OpenAI  기관 지급 크레딧 $5     → 달러로 막는다 (1회 $0.30 / 누적 $3.00)

기록은 llm_usage 테이블에 남고, 그게 그대로 비용 대시보드의 원본이 된다.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from app.config import get_settings
from app.db import connect
from app.llm.base import Usage
from app.llm.pricing import estimate_usd


class BudgetExceeded(RuntimeError):
    """상한 초과. 루프는 이걸 받으면 진행분을 보존하고 멈춘다."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason} — {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def utc_now() -> str:
    """SQLite date() 와 맞물리도록 UTC, 오프셋 없는 형식으로 남긴다."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class BudgetGuard:
    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id
        self.settings = get_settings()

    # ── 조회 ────────────────────────────────────────────────
    def snapshot(self) -> dict[str, float]:
        with closing(connect()) as conn:
            run_calls = 0
            run_usd = 0.0
            if self.run_id:
                r = conn.execute(
                    "SELECT COUNT(*) AS c, COALESCE(SUM(usd), 0) AS u "
                    "FROM llm_usage WHERE run_id = ?",
                    (self.run_id,),
                ).fetchone()
                run_calls, run_usd = r["c"], float(r["u"])

            r = conn.execute(
                "SELECT COUNT(*) AS c FROM llm_usage "
                "WHERE date(created_at) = date('now')"
            ).fetchone()
            day_calls = r["c"]

            r = conn.execute("SELECT COALESCE(SUM(usd), 0) AS u FROM llm_usage").fetchone()
            total_usd = float(r["u"])

        return {
            "run_calls": run_calls,
            "run_usd": run_usd,
            "day_calls": day_calls,
            "total_usd": total_usd,
        }

    # ── 검사 ────────────────────────────────────────────────
    def check(self) -> None:
        """호출 직전에 부른다. 넘었으면 BudgetExceeded 를 던진다."""
        s = self.settings
        n = self.snapshot()

        if n["run_calls"] >= s.max_llm_calls_per_run:
            raise BudgetExceeded(
                "실행당 LLM 호출 상한",
                f"{int(n['run_calls'])}/{s.max_llm_calls_per_run}회",
            )
        if n["day_calls"] >= s.max_llm_calls_per_day:
            raise BudgetExceeded(
                "일일 LLM 호출 상한",
                f"{int(n['day_calls'])}/{s.max_llm_calls_per_day}회",
            )
        if n["run_usd"] >= s.max_usd_per_run:
            raise BudgetExceeded(
                "실행당 비용 상한",
                f"${n['run_usd']:.4f}/${s.max_usd_per_run:.2f}",
            )
        if n["total_usd"] >= s.max_usd_total:
            raise BudgetExceeded(
                "누적 비용 상한",
                f"${n['total_usd']:.4f}/${s.max_usd_total:.2f}",
            )

    # ── 기록 ────────────────────────────────────────────────
    def record(self, provider: str, model: str, usage: Usage) -> float:
        """사용량을 남기고 달러를 돌려준다.

        기록은 부기(簿記)일 뿐이다. 여기서 실패했다고 이미 성공한 LLM 응답을
        통째로 버리면 안 된다. run_id 가 runs 에 없으면 NULL 로 남기고 계속 간다.
        """
        usd = estimate_usd(provider, model, usage.prompt_tokens, usage.completion_tokens)
        row = (provider, model, usage.prompt_tokens, usage.completion_tokens, usd, utc_now())
        sql = (
            "INSERT INTO llm_usage "
            "(run_id, provider, model, prompt_tokens, completion_tokens, usd, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        with closing(connect()) as conn, conn:
            try:
                conn.execute(sql, (self.run_id, *row))
            except sqlite3.IntegrityError:
                # 실행에 속하지 않은 호출 (스모크 테스트·워밍업 등)
                conn.execute(sql, (None, *row))
        return usd
