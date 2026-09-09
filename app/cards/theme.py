"""카드 디자인 시스템 (D-013).

프로처럼 보이는 건 그림이 아니라 **프레임**이다.
5장이 같은 배경·같은 상단바·같은 여백을 쓰면 세트로 읽힌다.
색은 늘리지 않는다. 배경 남색 + 흰 카드 + 강조 하나.

배경색은 생성된 캐릭터 이미지에서 **뽑아온 값**이다. 맞춘 게 아니라 가져왔다.
그래서 캐릭터를 얹어도 주변에 사각 경계가 생기지 않는다.
"""

from __future__ import annotations

from pathlib import Path

# ── 크기 ────────────────────────────────────────────────────
CARD_W, CARD_H = 1080, 1350
MARGIN = 72                    # 카드 바깥 여백. 꽉 채우지 않는다
HEADER_H = 96

# ── 색 (캐릭터 배경에서 추출) ───────────────────────────────
NAVY_TOP = (7, 19, 35)         # #071323
NAVY_MID = (9, 22, 41)         # #091629
NAVY_BOT = (25, 42, 72)        # #192A48

PAPER = (255, 255, 255)
PAPER_EDGE = (226, 230, 238)
INK = (24, 28, 38)             # 본문 검정
INK_SOFT = (58, 66, 82)        # 보조 설명. 흐린 회색은 시니어에게 안 읽힌다
ACCENT = (26, 105, 202)        # 강조 파랑 — 제목의 핵심 단어에만. 흰 바탕 대비 5.36:1
GOLD = (232, 185, 106)         # 표지 제목 아래쪽에만
WHITE_DIM = (206, 214, 228)    # 상단바 글씨

# ── 폰트 ────────────────────────────────────────────────────
# Pretendard (SIL Open Font License 1.1) 를 저장소에 동봉했다.
# OFL 은 재배포를 허용하므로 다른 컴퓨터에서도 그대로 돈다.
#
# 맑은 고딕은 Windows 기본 폰트라 재배포할 수 없어 파일을 넣지 않았다.
# 폰트가 아예 없는 환경을 위한 마지막 대비로만 남겨 둔다.
FONT_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"

FONT_CANDIDATES = {
    "bold": [
        FONT_DIR / "Pretendard-ExtraBold.otf",
        Path("C:/Windows/Fonts/malgunbd.ttf"),
    ],
    "medium": [
        FONT_DIR / "Pretendard-Medium.otf",
        Path("C:/Windows/Fonts/malgun.ttf"),
    ],
}

# 시니어 대상이라 글자 크기에 **하한**을 둔다 (PRD 2장)
SIZE = {
    "cover_title": 108,
    "cover_sub": 40,
    "badge": 34,
    "title": 66,
    "body": 44,        # 본문
    "note": 38,        # 보조
    "header": 28,
}

# 검사 기준 — 카드를 내보내기 전에 코드가 직접 잰다.
# 사람이 눈으로 확인하는 대신 기계가 막는다.
MIN_BODY_SIZE = 38          # 본문이 이보다 작으면 카드를 내보내지 않는다
MIN_CONTRAST = 4.5          # 배경 대비 명암비 하한 (WCAG AA)
MOBILE_PREVIEW_W = 360      # 스마트폰에서 보이는 실제 폭. 이 크기로 줄여 확인한다


def _channel(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def font_path(weight: str) -> str:
    for p in FONT_CANDIDATES[weight]:
        if p.exists():
            return str(p)
    raise FileNotFoundError(f"쓸 수 있는 폰트가 없다: {weight}")
