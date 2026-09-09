"""화면 라우트. 지금은 화면 1(시작)과 상태 점검만 있다."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.db import EXPECTED_TABLES, table_names

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATE_DIR)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def start(request: Request):
    return templates.TemplateResponse(request, "start.html", {"title": "시작"})


@router.get("/healthz")
async def healthz():
    """서버가 떴다는 것만으로 성공 처리하지 않는다. DB 테이블까지 확인한다.

    강의 자료가 반복 경고한 함정 3번 — "종료 코드 0 != 성공".
    """
    try:
        found = set(table_names())
    except Exception as exc:  # noqa: BLE001 - 기동 점검이라 원인을 그대로 보여준다
        return JSONResponse({"status": "error", "db": f"error: {exc}"}, status_code=500)

    missing = sorted(set(EXPECTED_TABLES) - found)
    s = get_settings()
    body = {
        "status": "ok" if not missing else "error",
        "db": "ok" if not missing else f"missing tables: {missing}",
        "tables": sorted(found),
        "provider": s.llm_provider,
        "line_send_enabled": s.line_send_enabled,
    }
    return JSONResponse(body, status_code=200 if not missing else 500)
