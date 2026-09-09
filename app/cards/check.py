"""카드 검사 — 사람 눈 대신 코드가 잰다.

"만들었다"와 "읽힌다"는 다르다. 내보내기 전에 기계가 막는다.

  1. 글자 크기 하한        시니어가 못 읽는 크기면 통과 못 시킨다
  2. 배경 대비 명암비      흐린 색 조합을 잡는다 (WCAG AA 4.5:1)
  3. 스마트폰 축소본       360px 로 줄여 실제 보이는 크기를 남긴다
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.cards.theme import (
    ACCENT,
    INK,
    INK_SOFT,
    MIN_BODY_SIZE,
    MIN_CONTRAST,
    MOBILE_PREVIEW_W,
    NAVY_TOP,
    PAPER,
    SIZE,
    WHITE_DIM,
    contrast,
)


@dataclass
class Issue:
    where: str
    detail: str

    def __str__(self) -> str:
        return f"{self.where}: {self.detail}"


# 실제로 쓰이는 (글자색, 바탕색) 짝
_PAIRS = {
    "본문 / 흰 종이": (INK_SOFT, PAPER),
    "제목 / 흰 종이": (INK, PAPER),
    "강조어 / 흰 종이": (ACCENT, PAPER),
    "상단바 / 남색": (WHITE_DIM, NAVY_TOP),
    "표지 제목 / 남색": ((255, 255, 255), NAVY_TOP),
}

_TEXT_SIZES = ("body", "note")


def check_theme() -> list[Issue]:
    """디자인 시스템 자체를 검사한다. 카드를 만들기 전에 한 번 돌린다."""
    issues: list[Issue] = []

    for name, (fg, bg) in _PAIRS.items():
        ratio = contrast(fg, bg)
        if ratio < MIN_CONTRAST:
            issues.append(Issue(name, f"명암비 {ratio:.2f} < {MIN_CONTRAST} — 흐려서 안 읽힌다"))

    for key in _TEXT_SIZES:
        if SIZE[key] < MIN_BODY_SIZE:
            issues.append(Issue(f"글자 크기 {key}", f"{SIZE[key]}px < 하한 {MIN_BODY_SIZE}px"))

    return issues


def theme_report() -> list[tuple[str, float, bool]]:
    """명암비를 표로 뽑는다. 통과 여부까지."""
    out = []
    for name, (fg, bg) in _PAIRS.items():
        r = contrast(fg, bg)
        out.append((name, r, r >= MIN_CONTRAST))
    return out


def mobile_preview(src: Path | str, dst: Path | str, width: int = MOBILE_PREVIEW_W) -> tuple[int, int]:
    """스마트폰에서 보이는 크기로 줄인 사본. 여기서 안 읽히면 실패다."""
    im = Image.open(src)
    h = round(im.height * width / im.width)
    small = im.resize((width, h), Image.LANCZOS)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    small.save(dst)
    return small.size


def contact_sheet(paths: list[Path | str], dst: Path | str, width: int = MOBILE_PREVIEW_W) -> None:
    """카드 여러 장을 축소해 한 장에 늘어놓는다. 세트로 보이는지 확인용."""
    ims = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        ims.append(im.resize((width, round(im.height * width / im.width)), Image.LANCZOS))
    if not ims:
        return
    gap = 16
    sheet = Image.new("RGB", (sum(i.width for i in ims) + gap * (len(ims) + 1),
                              max(i.height for i in ims) + gap * 2), (238, 240, 244))
    x = gap
    for im in ims:
        sheet.paste(im, (x, gap))
        x += im.width + gap
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dst)
