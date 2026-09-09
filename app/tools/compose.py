"""카드 합성 도구 (로컬, Pillow). 쓰기 권한은 `output/<실행ID>/` 안으로만.

글자는 이미지 모델에 맡기지 않고 코드로 얹는다 (D-004).
문구만 고칠 때 이미지를 다시 만들 필요가 없고, 글자 크기를 강제할 수 있다.

**"만들었다"와 "파일이 열린다"는 다르다.** 저장한 뒤 실제로 다시 열어 크기를 확인하고,
글자 크기·명암비 검사를 통과해야만 성공으로 본다.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.cards.check import check_theme, mobile_preview
from app.cards.render import content, cover
from app.cards.theme import CARD_H, CARD_W
from app.config import get_settings
from app.tools.base import Failure, OnFail, Permission, Tool, ToolResult, registry

ASSETS = Path(__file__).resolve().parent.parent.parent / "assets" / "character"
POSES = {
    "greet": ASSETS / "pose_greet.png",
    "point": ASSETS / "pose_point_left.png",   # 오른쪽에 서므로 왼쪽(글)을 가리킨다
    "open": ASSETS / "pose_open.png",
    "none": None,
}

PARAMS = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string", "description": "이 실행의 ID. 저장 폴더가 된다."},
        "section": {"type": "string", "description": "상단바에 표시할 분야. 예) 건강, 복지, 날씨",
                    "default": "생활정보"},
        "cards": {
            "type": "array",
            "description": "카드 5장의 내용. 첫 장은 표지(kind=cover)로 한다.",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["cover", "content"],
                             "description": "cover 는 표지, content 는 본문"},
                    "no": {"type": "integer", "description": "본문 카드 번호 (1부터)"},
                    "title": {"type": "string",
                              "description": "제목. 한 줄에 들어가게 20자 이내를 권한다"},
                    "title_bottom": {"type": "string",
                                     "description": "표지 제목 둘째 줄 (kind=cover 일 때)"},
                    "badge": {"type": "string", "description": "표지 위 작은 부제"},
                    "highlight": {"type": "string",
                                  "description": "제목에서 파랗게 강조할 부분"},
                    "body": {"type": "string",
                             "description": "본문. 짧고 쉬운 말로. 한 카드에 메시지 하나만"},
                    "bullets": {"type": "array", "items": {"type": "string"},
                                "description": "목록 항목 (선택)"},
                    "check": {"type": "string",
                              "description": "'꼭 기억하세요' 박스에 넣을 한 문장 (선택)"},
                    "pose": {"type": "string", "enum": ["greet", "point", "open", "none"],
                             "description": "캐릭터 자세. 표지는 greet, 목록은 open 을 권한다"},
                },
                "required": ["kind"],
            },
        },
    },
    "required": ["run_id", "cards"],
}

DESCRIPTION = (
    "카드뉴스 이미지를 만든다. 배경·캐릭터·글자를 코드로 합성해 1080x1350 PNG 로 저장한다. "
    "시니어가 읽을 수 있게 글자 크기와 명암비를 자동으로 검사하고, 통과하지 못하면 실패로 돌려준다. "
    "제목은 짧게(20자 이내) 쓸수록 줄바꿈이 예쁘다. 한 카드에는 메시지를 하나만 담는다. "
    "날짜는 '내일' 대신 '9월 15일 월요일' 처럼 명시한다."
)


def _out_dir(run_id: str) -> Path:
    """쓰기는 output/<실행ID>/ 안으로만. 경로를 벗어나면 거부한다."""
    root = get_settings().output_path.resolve()
    safe = "".join(c for c in run_id if c.isalnum() or c in "-_")[:64] or "run"
    d = (root / safe).resolve()
    if not str(d).startswith(str(root)):
        raise ValueError("허용된 폴더 밖으로 쓰려고 했다")
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _compose(run_id: str, cards: list[dict], section: str = "생활정보") -> ToolResult:
    issues = check_theme()
    if issues:
        return ToolResult(ok=False,
                          summary="디자인 검사 실패: " + "; ".join(map(str, issues)),
                          error_label=Failure.TOOL_ERROR)

    out = _out_dir(run_id)
    made: list[str] = []

    for i, c in enumerate(cards, start=1):
        pose = POSES.get(c.get("pose", "point"), POSES["point"])
        if c.get("kind") == "cover":
            img = cover(
                title_top=c.get("title", ""),
                title_bot=c.get("title_bottom", ""),
                badge=c.get("badge", ""),
                section=section,
                char_path=pose,
            )
        else:
            img = content(
                no=int(c.get("no", i - 1) or i - 1),
                title=c.get("title", ""),
                highlight=c.get("highlight"),
                body=c.get("body", ""),
                bullets=c.get("bullets"),
                check=c.get("check"),
                section=section,
                char_path=pose,
            )
        p = out / f"card_{i:02d}.png"
        img.save(p)
        made.append(str(p))

    # "저장했다" 를 믿지 않고 다시 열어 확인한다
    bad = []
    for p in made:
        try:
            with Image.open(p) as im:
                if im.size != (CARD_W, CARD_H):
                    bad.append(f"{Path(p).name} 크기 {im.size}")
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{Path(p).name} 열기 실패({type(exc).__name__})")

    if bad:
        return ToolResult(ok=False, summary="파일 확인 실패: " + ", ".join(bad),
                          error_label=Failure.IMAGE_FAILED)

    # 스마트폰 크기 축소본 — 작은 화면에서 읽히는지 눈으로 확인할 근거
    preview_dir = out / "mobile"
    for p in made:
        mobile_preview(p, preview_dir / Path(p).name)

    return ToolResult(
        ok=True,
        data={"files": made, "dir": str(out), "mobile": str(preview_dir)},
        summary=f"카드 {len(made)}장 생성·검증 완료 → {out}",
    )


compose_cards = registry.add(Tool(
    name="compose_cards",
    description=DESCRIPTION,
    parameters=PARAMS,
    handler=_compose,
    permission=Permission.WRITE_OUTPUT,
    on_fail=OnFail.RETRY,
    max_retry=1,
))
