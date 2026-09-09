"""카드 합성 — 배경 · 캐릭터 · 글자 3개 레이어 (D-004, D-013).

글자를 이미지 모델에 맡기지 않는다. 오타가 나고 수정이 안 되기 때문이다.
여기서 코드로 얹으면 문구만 고칠 때 이미지를 다시 만들지 않아도 된다.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.cards.theme import (
    ACCENT,
    CARD_H,
    CARD_W,
    GOLD,
    HEADER_H,
    INK,
    INK_SOFT,
    MARGIN,
    NAVY_BOT,
    NAVY_TOP,
    PAPER,
    SIZE,
    WHITE_DIM,
    font_path,
)

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(font_path(weight), size)
    return _font_cache[key]


# ── 배경 ────────────────────────────────────────────────────
def background() -> Image.Image:
    """캐릭터 이미지와 같은 세로 그라데이션. 위가 어둡고 아래가 밝다."""
    img = Image.new("RGB", (CARD_W, CARD_H), NAVY_TOP)
    d = ImageDraw.Draw(img)
    for y in range(CARD_H):
        t = (y / CARD_H) ** 1.4          # 아래쪽에서 빠르게 밝아진다
        c = tuple(round(a + (b - a) * t) for a, b in zip(NAVY_TOP, NAVY_BOT))
        d.line([(0, y), (CARD_W, y)], fill=c)
    return img


def header(img: Image.Image, section: str = "건강") -> None:
    """5장이 공유하는 상단바. 세트로 보이게 만드는 핵심."""
    d = ImageDraw.Draw(img)
    f = font("bold", SIZE["header"])
    left = f"생활정보 카드뉴스   |   {section}"
    d.text((MARGIN, HEADER_H // 2), left, font=f, fill=WHITE_DIM, anchor="lm")
    d.text((CARD_W - MARGIN, HEADER_H // 2), "손주가 알려드려요",
           font=f, fill=WHITE_DIM, anchor="rm")


def dot_pattern(img: Image.Image, x: int, y: int, cols=5, rows=3, gap=26, r=4) -> None:
    """빈 곳을 채우는 점 패턴. 여백을 '의도된 여백'으로 만든다."""
    d = ImageDraw.Draw(img)
    for i in range(cols):
        for j in range(rows):
            cx, cy = x + i * gap, y + j * gap
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(70, 90, 130))


# ── 흰 카드 ─────────────────────────────────────────────────
def paper(img: Image.Image, top: int, height: int, radius: int = 28) -> tuple[int, int, int, int]:
    """남색 위에 얹는 흰 종이. 그림자를 깔아 떠 보이게 한다."""
    box = (MARGIN, top, CARD_W - MARGIN, top + height)

    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [box[0] + 6, box[1] + 14, box[2] + 6, box[3] + 14], radius, fill=(0, 0, 0, 110)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    img.paste(Image.alpha_composite(img.convert("RGBA"), shadow).convert("RGB"), (0, 0))

    ImageDraw.Draw(img).rounded_rectangle(box, radius, fill=PAPER)
    return box


def number_badge(img: Image.Image, cx: int, cy: int, n: int, r: int = 34) -> None:
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=NAVY_BOT)
    d.text((cx, cy + 1), f"{n:02d}", font=font("bold", SIZE["badge"]),
           fill=(255, 255, 255), anchor="mm")


# ── 글자 ────────────────────────────────────────────────────
def clean(text: str) -> str:
    """모델이 넣은 줄바꿈 표기를 지운다.

    LLM 이 본문에 줄바꿈을 문자 그대로 적어 넣는 일이 있다.
    그대로 그리면 카드에 백슬래시 n 이 찍힌다. 실제로 그렇게 나왔다.
    줄바꿈은 wrap 이 폭을 보고 알아서 하므로 공백으로 바꾼다.
    """
    if not text:
        return ""
    bs = chr(92)
    for token in (bs + "r" + bs + "n", bs + "n", bs + "r", bs + "t"):
        text = text.replace(token, " ")
    for ch in (chr(13), chr(10), chr(9)):
        text = text.replace(ch, " ")
    return " ".join(text.split())


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """한글은 어절 단위로 끊는다."""
    lines, cur = [], ""
    for word in clean(text).split():
        trial = f"{cur} {word}".strip()
        if f.getlength(trial) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_title(d: ImageDraw.ImageDraw, y: int, text: str, highlight: str | None,
               max_w: int, size: int) -> int:
    """제목. highlight 로 지정한 부분만 강조색으로 칠한다.

    강조어가 줄바꿈으로 갈라져도 칠해지도록 **어절 단위**로 판단한다.
    한 줄 안에 통째로 있을 때만 칠하면, 긴 제목에서 강조가 통째로 사라진다.
    """
    f = font("bold", size)
    line_h = int(size * 1.34)
    marked = set((highlight or "").split())

    for line in wrap(text, f, max_w):
        words = line.split()
        if marked and any(w in marked for w in words):
            space = f.getlength(" ")
            total = sum(f.getlength(w) for w in words) + space * (len(words) - 1)
            x = CARD_W // 2 - total / 2
            for i, w in enumerate(words):
                d.text((x, y), w, font=f, fill=ACCENT if w in marked else INK, anchor="lt")
                x += f.getlength(w) + (space if i < len(words) - 1 else 0)
        else:
            d.text((CARD_W // 2, y), line, font=f, fill=INK, anchor="mt")
        y += line_h
    return y


def draw_body(d: ImageDraw.ImageDraw, y: int, text: str, max_w: int,
              size: int, color=INK_SOFT) -> int:
    f = font("medium", size)
    line_h = int(size * 1.62)          # 행간을 넉넉히. 시니어 가독성
    for line in wrap(text, f, max_w):
        d.text((CARD_W // 2, y), line, font=f, fill=color, anchor="mt")
        y += line_h
    return y


# ── 캐릭터 ──────────────────────────────────────────────────
def paste_character(img: Image.Image, char_path: Path, height: int,
                    cx: int, bottom: int) -> bool:
    """캐릭터를 얹는다. cx 는 가로 중심, bottom 은 발이 닿을 y.

    배경이 제거된 RGBA 를 기대한다. 투명 영역이 없으면 얹지 않고 False 를 돌려준다 —
    사각형 얼룩을 조용히 남기느니 안 넣고 알리는 편이 낫다.
    """
    ch = Image.open(char_path)
    if ch.mode != "RGBA" or ch.getchannel("A").getextrema()[0] == 255:
        return False

    ratio = height / ch.height
    ch = ch.resize((max(1, round(ch.width * ratio)), height), Image.LANCZOS)
    img.paste(ch, (cx - ch.width // 2, bottom - ch.height), ch)
    return True


# ── 카드 종류 ───────────────────────────────────────────────
def cover(title_top: str, title_bot: str, badge: str, section: str = "건강",
          char_path: Path | None = None) -> Image.Image:
    img = background()
    header(img, section)
    d = ImageDraw.Draw(img)

    # 부제 뱃지
    f = font("medium", SIZE["cover_sub"])
    tw = f.getlength(badge)
    bx0, by0 = CARD_W // 2 - tw / 2 - 34, 170
    d.rounded_rectangle([bx0, by0, bx0 + tw + 68, by0 + 74], 37,
                        outline=WHITE_DIM, width=2)
    d.text((CARD_W // 2, by0 + 37), badge, font=f, fill=WHITE_DIM, anchor="mm")

    ft = font("bold", SIZE["cover_title"])
    line_h = int(SIZE["cover_title"] * 1.24)
    d.text((CARD_W // 2, 286), title_top, font=ft, fill=(255, 255, 255), anchor="mt")
    d.text((CARD_W // 2, 286 + line_h), title_bot, font=ft, fill=GOLD, anchor="mt")

    dot_pattern(img, CARD_W - MARGIN - 110, 132)
    dot_pattern(img, MARGIN, CARD_H - 300, cols=3, rows=4)

    if char_path and Path(char_path).exists():
        paste_character(img, Path(char_path), 700, CARD_W // 2, CARD_H - 24)
    return img


def content(no: int, title: str, highlight: str | None, body: str,
            bullets: list[str] | None = None, check: str | None = None,
            section: str = "건강", char_path: Path | None = None) -> Image.Image:
    """흰 종이 높이를 내용에 맞춰 잰 뒤 그린다. 고정하면 아래가 텅 빈다."""
    img = background()
    header(img, section)

    inner_w = CARD_W - 2 * MARGIN - 120
    ft, fb = font("bold", SIZE["title"]), font("medium", SIZE["body"])
    fn = font("medium", SIZE["note"])

    title_h = len(wrap(title, ft, inner_w)) * int(SIZE["title"] * 1.34)
    body_h = len(wrap(body, fb, inner_w)) * int(SIZE["body"] * 1.62)
    bullets_h = (30 + len(bullets) * int(SIZE["body"] * 1.55)) if bullets else 0
    check_h = 0
    if check:
        check_lines = len(wrap(check, fn, inner_w - 200))
        check_h = 40 + 60 + check_lines * int(SIZE["note"] * 1.55) + 44

    PAD_TOP, PAD_BOT = 148, 76          # 번호 뱃지 자리 / 아래 여백
    top = 168
    needed = PAD_TOP + title_h + 26 + body_h + bullets_h + check_h + PAD_BOT
    paper_h = min(needed, CARD_H - top - 150)

    box = paper(img, top, paper_h)
    d = ImageDraw.Draw(img)
    number_badge(img, CARD_W // 2, top + 74, no)

    y = top + PAD_TOP
    y = draw_title(d, y, title, highlight, inner_w, SIZE["title"])
    y += 26
    y = draw_body(d, y, body, inner_w, SIZE["body"])

    if bullets:
        y += 30
        for b in bullets:
            d.text((CARD_W // 2, y), f"·  {b}", font=fb, fill=INK, anchor="mt")
            y += int(SIZE["body"] * 1.55)

    if check:
        y += 40
        bh = check_h - 84
        d.rectangle([box[0] + 60, y, box[2] - 60, y + bh], outline=INK, width=3)
        lw = font("bold", SIZE["note"]).getlength("꼭 기억하세요")
        d.rectangle([box[0] + 92, y - 26, box[0] + 92 + lw + 48, y + 26], fill=ACCENT)
        d.text((box[0] + 92 + 24, y), "꼭 기억하세요",
               font=font("bold", SIZE["note"]), fill=(255, 255, 255), anchor="lm")
        draw_body(d, y + 60, check, inner_w - 200, SIZE["note"], color=INK)

    # 캐릭터는 흰 종이 **아래쪽 남색 영역**에 둔다. 글을 가리면 안 된다.
    if char_path and Path(char_path).exists():
        paper_bottom = top + paper_h
        room = CARD_H - 40 - paper_bottom
        h = max(200, min(380, room + 110))       # 종이에 살짝만 걸친다
        paste_character(img, Path(char_path), h, CARD_W - MARGIN - 120, CARD_H - 40)
    return img
