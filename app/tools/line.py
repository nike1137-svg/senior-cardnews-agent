"""LINE 발송 도구 — 🔴 되돌릴 수 없는 작업 (D-005).

**3중 잠금**
  1. 기본값이 `dry-run`. 아무것도 안 보낸다
  2. 실제 발송은 환경변수 `LINE_SEND_ENABLED=true`
  3. 그리고 사람이 화면에서 승인 (`approved=True`)

세 개가 **모두** 충족될 때만 나간다. 채점자가 버튼을 눌러도 시니어에게 가면 안 된다.

**실패해도 자동 재시도하지 않는다.** 중복 발송 위험이 있어서 일부러 뺐다.
사람이 화면에서 다시 누르게 한다.
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.tools import faults
from app.tools.base import Failure, OnFail, Permission, Tool, ToolResult, registry

PARAMS = {
    "type": "object",
    "properties": {
        "image_paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "보낼 카드 이미지 파일 경로 목록",
        },
        "message": {"type": "string", "description": "함께 보낼 짧은 안내 문구"},
        "approved": {
            "type": "boolean",
            "description": "사람이 화면에서 발송을 승인했는가. 에이전트가 스스로 true 로 만들면 안 된다.",
            "default": False,
        },
    },
    "required": ["image_paths"],
}

DESCRIPTION = (
    "완성된 카드뉴스를 LINE 으로 보낸다. 🔴 되돌릴 수 없는 작업이다. "
    "기본은 실제로 보내지 않는 dry-run 이며, 사람의 승인과 환경변수 스위치가 "
    "모두 있을 때만 실제로 나간다. 에이전트가 임의로 승인하지 말 것. "
    "실패해도 다시 시도하지 않는다 — 중복 발송 위험이 있으므로 사람이 다시 누르게 한다."
)


async def _send(image_paths: list[str], message: str = "", approved: bool = False) -> ToolResult:
    s = get_settings()
    files = [Path(p) for p in (image_paths or [])]
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        return ToolResult(ok=False, summary=f"보낼 파일이 없다: {missing}",
                          error_label=Failure.TOOL_ERROR)

    locks = {
        "사람 승인": approved,
        "환경변수 LINE_SEND_ENABLED": s.line_send_enabled,
        "채널 토큰": bool(s.line_channel_access_token),
    }
    blocked = [k for k, v in locks.items() if not v]

    if blocked:
        return ToolResult(
            ok=True,          # dry-run 은 정상 동작이다. 실패가 아니다
            data={"mode": "dry-run", "count": len(files), "blocked": blocked},
            summary=(f"[dry-run] 실제 발송하지 않음. 카드 {len(files)}장. "
                     f"잠긴 조건: {', '.join(blocked)}"),
        )

    if faults.should_fail("line_fail"):
        return ToolResult(ok=False, summary="[주입된 실패] 발송 실패 — 자동 재시도하지 않음",
                          error_label=Failure.TOOL_ERROR)

    # 세 잠금이 모두 풀린 실제 발송 경로.
    # 실채널 연동은 시연 계획이 확정된 뒤에 붙인다 (PRD 9장 3번).
    return ToolResult(
        ok=False,
        summary="실발송 경로가 아직 연결되지 않았다. dry-run 으로만 검증됨",
        error_label=Failure.TOOL_ERROR,
    )


send_line = registry.add(Tool(
    name="send_line",
    description=DESCRIPTION,
    parameters=PARAMS,
    handler=_send,
    permission=Permission.EXTERNAL_SEND,
    on_fail=OnFail.STOP,     # 🔴 재시도 금지
    max_retry=0,
    needs_approval=True,
))
