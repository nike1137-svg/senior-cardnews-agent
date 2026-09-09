"""SQLite 연결과 스키마 초기화.

상태 정본이다 (D-012). trace.json / outcome.json 은 여기서 내보낸다.
WAL 모드인 이유: SSE 읽기와 에이전트 루프 쓰기가 동시에 일어난다.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from app.config import get_settings

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# healthz 가 확인하는 목록. 하나라도 없으면 기동 실패로 본다.
EXPECTED_TABLES = ("runs", "steps", "tool_calls", "questions", "llm_usage")


def connect() -> sqlite3.Connection:
    s = get_settings()
    s.ensure_dirs()
    conn = sqlite3.connect(s.db_file, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with closing(connect()) as conn, conn:
        conn.executescript(sql)


def table_names() -> list[str]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [r["name"] for r in rows]
