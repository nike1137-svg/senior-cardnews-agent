"""화면 라우트."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.agent import runner, state
from app.config import get_settings
from app.db import EXPECTED_TABLES, table_names
from app.tools import faults

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATE_DIR)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def start(request: Request):
    return templates.TemplateResponse(request, "start.html", {
        "title": "시작",
        "fault_banner": faults.banner(),
        "recent": state.list_runs(limit=5),
    })


@router.get("/runs", response_class=HTMLResponse)
async def run_list(request: Request):
    runs = state.list_runs(limit=50)
    rows = [{"run": r, "usage": state.usage_of(r.run_id)} for r in runs]
    return templates.TemplateResponse(request, "runs.html", {
        "title": "실행 기록", "rows": rows,
    })


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: str, stale: int = 0):
    run = state.get_run(run_id)
    if run is None:
        return templates.TemplateResponse(request, "missing.html",
                                          {"title": "없는 실행", "run_id": run_id},
                                          status_code=404)
    out = get_settings().output_path / run_id
    cards = [f"/output/{run_id}/{p.name}" for p in sorted(out.glob("card_*.png"))] if out.exists() else []

    return templates.TemplateResponse(request, "run.html", {
        "title": "진행",
        "run": run,
        "cards": cards,
        "question": state.open_question(run_id),
        "answers": state.answers_of(run_id),
        "steps": state.step_timing(run_id),
        "logs": state.logs_after(run_id, 0),
        "usage": state.usage_of(run_id),
        "stale": bool(stale),
        "working": runner.is_running(run_id),
        "fault_banner": faults.banner(),
    })


@router.get("/healthz")
async def healthz():
    """서버가 떴다는 것만으로 성공 처리하지 않는다. DB 테이블까지 확인한다."""
    try:
        found = set(table_names())
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "error", "db": f"error: {exc}"}, status_code=500)

    missing = sorted(set(EXPECTED_TABLES) - found)
    s = get_settings()
    body = {
        "status": "ok" if not missing else "error",
        "db": "ok" if not missing else f"missing tables: {missing}",
        "tables": sorted(found),
        "provider": s.llm_provider,
        "line_send_enabled": s.line_send_enabled,
        "fault_inject": sorted(faults.active()),
    }
    return JSONResponse(body, status_code=200 if not missing else 500)
