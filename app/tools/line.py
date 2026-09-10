"""LINE 발송 도구 — 🔴 되돌릴 수 없는 작업 (D-005).

**잠금 네 개가 모두 풀려야 나간다**
  1. 기본값이 `dry-run`. 아무것도 안 보낸다
  2. 환경변수 `LINE_SEND_ENABLED=true`
  3. 사람이 화면에서 승인 (`approved=True`)
  4. 수신자(`LINE_TO`)가 지정되어 있어야 한다

넷 중 하나라도 비면 dry-run 이다. 채점자가 버튼을 눌러도 시니어에게 가면 안 된다.
수신자를 명시하게 한 이유는, 친구 전체에게 보내는 broadcast 를 쓰면
나중에 대상이 늘어났을 때 사고가 되기 때문이다.

**보내기 전에 이미지가 밖에서 열리는지 먼저 확인한다.**
LINE 은 못 여는 URL 을 받아도 요청 자체는 200 을 돌려주고 사용자 화면에서만 조용히 깨진다.
"요청이 성공했다"와 "실제로 갔다"는 다르다.

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
    "완성된 카드뉴스를 LINE 으로 보낸다. 되돌릴 수 없는 작업이다. "
    "기본은 실제로 보내지 않는 dry-run 이며, 사람의 승인·환경변수 스위치·채널 토큰·수신자가 "
    "모두 갖춰졌을 때만 실제로 나간다. 에이전트가 approved 를 스스로 true 로 만들지 말 것. "
    "실패해도 다시 시도하지 않는다 — 중복 발송 위험이 있으므로 사람이 다시 누르게 한다."
)


PUSH_URL = "https://api.line.me/v2/bot/message/push"
MAX_MESSAGES = 5          # LINE 한 번에 보낼 수 있는 메시지 수


def _public_url(p: Path) -> str | None:
    """로컬 파일 경로를 공개 https 주소로 바꾼다.

    LINE 은 이미지를 URL 로만 받는다. 파일을 올려 주는 방식이 아니다.
    output/ 아래가 아니면 공개 주소가 없으므로 None 을 돌려준다.
    """
    s = get_settings()
    try:
        rel = p.resolve().relative_to(s.output_path.resolve())
    except ValueError:
        return None
    return f"{s.public_base_url.rstrip('/')}/output/{rel.as_posix()}"


async def _reachable(client, url: str) -> bool:
    """밖에서 실제로 열리는지 확인한다.

    LINE 은 못 여는 URL 을 받아도 요청 자체는 200 을 돌려주고,
    사용자 화면에서만 조용히 깨진다. 보내기 전에 우리가 먼저 확인한다.
    """
    try:
        r = await client.get(url, timeout=15, follow_redirects=True)
        return r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")
    except Exception:  # noqa: BLE001
        return False


def _resolve(image_paths: list[str]) -> tuple[list[Path], str]:
    """모델이 준 경로를 실제 파일로 맞춘다.

    **모델은 파일명을 지어낸다.** 실제 파일이 `card_01.png` 인데 `card1.png` 을 불렀다.
    저장 폴더 이름을 앱이 정하게 한 것과 같은 이유다 — 모델이 정하게 열어 두면 지어낸다.
    모델이 준 것 중 믿는 것은 **어느 실행 폴더인가** 까지이고, 파일 목록은 앱이 직접 읽는다.

    실제 파일이 다 있으면 그대로 쓴다. 없을 때만 폴더에서 찾고, 찾았다는 사실을 밝힌다.
    """
    given = [Path(p) for p in (image_paths or [])]
    if given and all(p.exists() for p in given):
        return given, ""

    for d in {p.parent for p in given if p.parent.name.startswith("run-")}:
        found = sorted(d.glob("card_*.png"))
        if found:
            return found, (f"모델이 준 파일명이 실제와 달라 폴더에서 직접 찾았다 "
                           f"({d.name}, {len(found)}장). ")
    return given, ""


async def _send(image_paths: list[str], message: str = "", approved: bool = False) -> ToolResult:
    s = get_settings()
    files, fixed = _resolve(image_paths)
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        return ToolResult(ok=False, summary=f"보낼 파일이 없다: {missing}",
                          error_label=Failure.TOOL_ERROR)

    locks = {
        "사람 승인": approved,
        "환경변수 LINE_SEND_ENABLED": s.line_send_enabled,
        "채널 토큰": bool(s.line_channel_access_token),
        "수신자 지정": bool(s.line_to),
    }
    blocked = [k for k, v in locks.items() if not v]

    if blocked:
        return ToolResult(
            ok=True,          # dry-run 은 정상 동작이다. 실패가 아니다
            data={"mode": "dry-run", "count": len(files), "blocked": blocked},
            summary=(f"{fixed}[dry-run] 실제 발송하지 않음. 카드 {len(files)}장. "
                     f"잠긴 조건: {', '.join(blocked)}"),
        )

    if faults.should_fail("line_fail"):
        return ToolResult(ok=False, summary="[주입된 실패] 발송 실패 — 자동 재시도하지 않음",
                          error_label=Failure.TOOL_ERROR)

    # ── 여기부터 실제 발송 ──────────────────────────────────
    urls, no_url = [], []
    for f in files:
        u = _public_url(f)
        (urls.append(u) if u else no_url.append(f.name))
    if no_url:
        return ToolResult(ok=False,
                          summary=f"공개 주소를 만들 수 없는 파일: {no_url}. output/ 아래여야 한다",
                          error_label=Failure.TOOL_ERROR)

    import httpx

    async with httpx.AsyncClient() as client:
        unreachable = [u for u in urls if not await _reachable(client, u)]
        if unreachable:
            return ToolResult(
                ok=False,
                summary=("이미지 주소가 밖에서 열리지 않는다. 터널이 꺼져 있거나 "
                         f"PUBLIC_BASE_URL 이 틀렸다: {unreachable[:2]}"),
                error_label=Failure.TOOL_ERROR)

        messages: list[dict] = []
        if message.strip():
            messages.append({"type": "text", "text": message.strip()[:1000]})
        for u in urls:
            messages.append({"type": "image", "originalContentUrl": u, "previewImageUrl": u})

        headers = {"Authorization": f"Bearer {s.line_channel_access_token}",
                   "Content-Type": "application/json"}
        sent = 0
        for i in range(0, len(messages), MAX_MESSAGES):
            chunk = messages[i:i + MAX_MESSAGES]
            r = await client.post(PUSH_URL, headers=headers, timeout=30,
                                  json={"to": s.line_to, "messages": chunk})
            if r.status_code != 200:
                return ToolResult(
                    ok=False,
                    summary=(f"발송 실패 HTTP {r.status_code} — {r.text[:200]} "
                             f"(앞서 {sent}건은 이미 나갔다. 자동 재시도하지 않는다)"),
                    error_label=Failure.TOOL_ERROR)
            sent += len(chunk)

    return ToolResult(
        ok=True,
        data={"mode": "sent", "messages": sent, "images": len(urls)},
        summary=f"실제 발송 완료 — 메시지 {sent}건 (카드 {len(urls)}장)",
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
