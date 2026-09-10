"""senior-cardnews MCP 서버 (⭐확장3).

내 도메인의 운영 데이터를 MCP 도구로 노출한다. stdio 로 붙으므로
웹앱과 같은 호스트에서 돌고 배포 시 프로세스가 늘지 않는다.

    uv run python -m mcp_server.server
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

# MCP SDK 2.x 에서 FastMCP 가 MCPServer 로 이름이 바뀌었다.
from mcp.server.mcpserver import MCPServer

from mcp_server.profile import AUDIENCE, CARD_TEMPLATE

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "app.db"

mcp = MCPServer(
    name="senior-cardnews",
    instructions=(
        "시니어 카드뉴스 운영 데이터를 제공한다. "
        "새 주제를 고르기 전에 list_past_publications 로 최근에 다룬 주제를 확인하고, "
        "문구를 쓰기 전에 get_audience_profile 로 금지 표현과 말투를 확인한다."
    ),
)



# 발행일 판정은 한국 날짜 기준이다 (아래 list_past_publications 주석 참고).
KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)

def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(
        "CREATE TABLE IF NOT EXISTS publications ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, topic TEXT NOT NULL,"
        " section TEXT, region TEXT, card_count INTEGER NOT NULL DEFAULT 0,"
        " keywords TEXT, published_at TEXT NOT NULL, note TEXT)"
    )
    return c


@mcp.tool()
def list_past_publications(days: int = 90, keyword: str = "", limit: int = 20) -> dict:
    """과거에 발행한 카드뉴스 이력을 조회한다.

    새 주제를 고르기 전에 반드시 확인할 것. 최근에 이미 다룬 주제를 또 내보내면
    받는 사람이 같은 안내를 반복해서 받게 된다.

    Args:
        days: 며칠 이내를 볼지 (기본 90)
        keyword: 제목·키워드에 포함된 말로 거르기 (비우면 전체)
        limit: 최대 건수
    """
    # 발행일은 **사람이 쓰는 날짜**다. 저장은 UTC 로 두되(기계가 비교할 값),
    # "며칠 전에 다뤘나" 는 한국 날짜로 따져야 한다 — 밤 9시 이후 발행분이
    # UTC 로는 전날이 되어 하루씩 밀린다. 실제로 그런 기록이 있다.
    since = (_now_kst() - timedelta(days=max(1, days))).strftime("%Y-%m-%d")
    sql = "SELECT topic, section, region, card_count, keywords, published_at, note " \
          "FROM publications WHERE published_at >= ?"
    args: list = [since]
    if keyword.strip():
        sql += " AND (topic LIKE ? OR keywords LIKE ?)"
        args += [f"%{keyword.strip()}%"] * 2
    sql += " ORDER BY published_at DESC LIMIT ?"
    args.append(max(1, min(limit, 100)))

    with closing(_conn()) as c:
        rows = [dict(r) for r in c.execute(sql, args)]

    today = _now_kst().date()
    for r in rows:
        try:
            # 저장된 UTC 시각을 한국 시각으로 옮긴 뒤 날짜를 뽑는다
            utc = datetime.strptime(r["published_at"][:19], "%Y-%m-%d %H:%M:%S")
            d = utc.replace(tzinfo=timezone.utc).astimezone(KST).date()
            r["published_at_kst"] = d.strftime("%Y-%m-%d")
            r["days_ago"] = (today - d).days
        except ValueError:
            r["days_ago"] = None

    return {
        "count": len(rows),
        "since": since,
        "publications": rows,
        "hint": ("최근에 다룬 주제는 후순위로 내리고 사람에게 알릴 것"
                 if rows else "최근 발행 이력이 없다. 어떤 주제든 새로 다룰 수 있다"),
    }


@mcp.tool()
def get_audience_profile() -> dict:
    """시니어 독자의 특성과 글쓰기 규칙을 돌려준다.

    문구를 쓰기 전에 확인할 것. 금지 표현, 글자 크기 하한, 관심 주제가 들어 있다.
    """
    return AUDIENCE


@mcp.tool()
def get_card_template() -> dict:
    """카드 양식(크기·색·구조·캐릭터 자세 규칙)을 돌려준다.

    스토리보드를 짤 때 확인할 것. 카드 5장의 역할 배분과 자세 선택 근거가 들어 있다.
    """
    return CARD_TEMPLATE


@mcp.tool()
def record_publication(topic: str, section: str = "", region: str = "",
                       card_count: int = 0, keywords: str = "",
                       note: str = "", run_id: str = "") -> dict:
    """발행 결과를 기록한다. 다음 실행이 이걸 조회해 중복을 피한다.

    카드가 실제로 만들어지고 사람이 승인한 뒤에만 부를 것.

    Args:
        topic: 발행한 주제
        section: 분야 (건강·복지·날씨 등)
        region: 대상 지역
        card_count: 만든 카드 장수
        keywords: 쉼표로 구분한 키워드
        note: 남길 메모
        run_id: 이 발행을 만든 실행 ID
    """
    if not topic.strip():
        return {"ok": False, "error": "topic 이 비어 있다"}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with closing(_conn()) as c, c:
        cur = c.execute(
            "INSERT INTO publications "
            "(run_id, topic, section, region, card_count, keywords, published_at, note) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (run_id or None, topic.strip(), section, region, int(card_count or 0),
             keywords, now, note),
        )
    return {"ok": True, "id": cur.lastrowid, "published_at": now,
            "message": f"'{topic.strip()}' 발행 기록 완료"}


if __name__ == "__main__":
    mcp.run()
