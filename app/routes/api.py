"""동작 라우트 — 실행 시작 / 답변 제출 / 실행 로그 스트림.

로그는 SSE(Server-Sent Events)로 밀어준다. 폴링보다 가볍고, 브라우저 기본 기능이라
외부 라이브러리가 필요 없다. 배포 환경에서 CDN 이 막혀도 그대로 돈다.
"""

from __future__ import annotations

import asyncio
import io
import json
import zipfile

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from app.agent import runner, state, trace
from app.config import get_settings
from app.timefmt import to_kst

router = APIRouter()


@router.post("/runs")
async def start_run(topic: str = Form(...), region: str = Form("")):
    s = get_settings()
    model = s.gemini_model if s.llm_provider == "gemini" else s.openai_model
    run_id = state.create_run(topic.strip(), region.strip(), s.llm_provider, model)
    runner.kick(run_id)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@router.post("/runs/{run_id}/answer")
async def submit_answer(
    run_id: str,
    question_id: str = Form(...),
    version: int = Form(...),
    answer: list[str] = Form(default=[]),
    free_text: str = Form(""),
):
    """답을 저장하고 루프를 다시 깨운다.

    같은 답을 두 번 보내도 한 번만 실행된다 (state.answer 가 막는다).
    지난 질문에 뒤늦게 답하면 안내만 하고 새 작업을 시작하지 않는다.
    """
    # 🔴 빈 답은 받지 않는다. 선택지가 없는 질문은 직접 입력이 유일한 입력 수단인데,
    # 그대로 두면 빈 값이 저장되고 **에이전트가 알아서 해석**한다.
    # 실제로 발송 승인 질문이 선택지 없이 나온 적이 있다 — 되돌릴 수 없는 단계에서
    # "답을 받았다" 로 처리되면 안 된다. 답을 안 넣었으면 아직 안 물어본 것이다.
    if not answer and not free_text.strip():
        return RedirectResponse(f"/runs/{run_id}?empty=1", status_code=303)

    value: object = answer if len(answer) != 1 else answer[0]
    if free_text.strip():
        value = free_text.strip() if not answer else {"선택": value, "직접입력": free_text.strip()}

    try:
        state.answer(run_id, question_id, int(version), value)
    except state.StaleAnswer:
        return RedirectResponse(f"/runs/{run_id}?stale=1", status_code=303)

    runner.kick(run_id)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@router.post("/runs/{run_id}/resume")
async def resume(run_id: str):
    """멈춘 실행을 사람이 다시 밀어준다 (상한 도달·예외 뒤)."""
    run = state.get_run(run_id)
    if run and run.status in ("stopped", "failed"):
        state.clear_stop_reason(run_id)
        state.set_status(run_id, "running")
    runner.kick(run_id)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@router.get("/runs/{run_id}/cards.zip")
async def cards_zip(run_id: str):
    """완성된 카드를 한 번에 내려받는다."""
    d = get_settings().output_path / run_id
    files = sorted(d.glob("card_*.png")) if d.exists() else []
    if not files:
        return JSONResponse({"error": "만들어진 카드가 없습니다"}, status_code=404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, arcname=f.name)
        # 출처 기록을 함께 넣는다. 나중에 무엇을 근거로 만들었는지 확인할 수 있어야 한다
        z.writestr("outcome.json",
                   json.dumps(trace.build_outcome(run_id), ensure_ascii=False, indent=2))
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{run_id}-cards.zip"'},
    )


@router.get("/runs/{run_id}/trace.json")
async def trace_json(run_id: str):
    """도구 호출 순서·판단 근거·소요시간·토큰. 평가 표의 원본."""
    return JSONResponse(trace.build_trace(run_id))


@router.get("/runs/{run_id}/outcome.json")
async def outcome_json(run_id: str):
    """완주 여부·사람 개입 횟수·실패 라벨·병목 단계."""
    return JSONResponse(trace.build_outcome(run_id))


@router.post("/runs/{run_id}/export")
async def export_files(run_id: str):
    """runs/<실행ID>/ 아래로 두 파일을 떨군다."""
    trace.export(run_id)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


def _log_line(r: dict) -> dict:
    return {
        "id": r["id"],
        "at": to_kst(r["created_at"], "%H:%M:%S"),
        "step": r["step_no"],
        "tool": r["tool_name"],
        "reason": (r["reason"] or "")[:160],
        "summary": (r["output_summary"] or "")[:400],
        "ok": bool(r["ok"]),
        "label": r["error_label"],
        "ms": r["duration_ms"] or 0,
    }


@router.get("/runs/{run_id}/events")
async def events(run_id: str, request: Request, after: int = 0):
    """실행 로그 스트림. 도구명·호출 이유·결과·소요시간이 실시간으로 흐른다."""

    async def gen():
        last_id = after
        last_status = None
        yield ": connected\n\n"

        while True:
            if await request.is_disconnected():
                break

            for row in state.logs_after(run_id, last_id):
                last_id = row["id"]
                yield f"event: log\ndata: {json.dumps(_log_line(row), ensure_ascii=False)}\n\n"

            run = state.get_run(run_id)
            status = run.status if run else "gone"
            payload = {
                "status": status,
                "loop_count": run.loop_count if run else 0,
                "stop_reason": run.stop_reason if run else None,
                "usage": state.usage_of(run_id),
                "steps": state.step_timing(run_id),
                "changed": status != last_status,
            }
            yield f"event: status\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            last_status = status

            if status in ("done", "stopped", "failed", "waiting_for_user", "gone"):
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
