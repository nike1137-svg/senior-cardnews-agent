"""루프를 백그라운드에서 돌린다 (D-012: asyncio 백그라운드 태스크).

웹 요청은 즉시 돌려주고 루프는 뒤에서 돈다. 사람이 답을 넣으면 다시 깨운다.

**재시작 복구** — 태스크는 프로세스가 죽으면 사라지지만 상태 정본은 SQLite 에 있다.
서버가 다시 뜨면 `running` 인 실행을 찾아 중단 지점부터 이어간다 (루브릭 3번).
"""

from __future__ import annotations

import asyncio
import logging

from app.agent import state
from app.agent.loop import AgentLoop

log = logging.getLogger("agent.runner")

_tasks: dict[str, asyncio.Task] = {}


async def _drive(run_id: str) -> None:
    try:
        await AgentLoop(run_id).run_until_blocked(max_ticks=40)
    except Exception:  # noqa: BLE001 - 배경 작업이 조용히 죽으면 안 된다
        log.exception("루프가 예외로 멈춤: %s", run_id)
        state.set_status(run_id, "failed", "루프 예외")


def kick(run_id: str) -> bool:
    """이미 돌고 있으면 건드리지 않는다. 새로 시작했으면 True."""
    task = _tasks.get(run_id)
    if task and not task.done():
        return False
    t = asyncio.create_task(_drive(run_id))
    _tasks[run_id] = t
    t.add_done_callback(lambda _: _tasks.pop(run_id, None))
    return True


def is_running(run_id: str) -> bool:
    task = _tasks.get(run_id)
    return bool(task and not task.done())


async def recover() -> list[str]:
    """서버 기동 시 호출. 끊긴 실행을 이어 붙인다."""
    resumed = []
    for run in state.list_runs(limit=50):
        if run.status == "running":
            kick(run.run_id)
            resumed.append(run.run_id)
    if resumed:
        log.info("중단됐던 실행 %d건을 이어서 진행: %s", len(resumed), resumed)
    return resumed
