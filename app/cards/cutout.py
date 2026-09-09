"""캐릭터 배경 제거 (누끼).

생성된 캐릭터는 단색 배경 위에 있다. 그대로 얹으면 흰 카드 위에 사각형 얼룩이 남는다.

네 모서리에서 **연결된 영역만** 채워 나간다(flood fill). 색 거리로만 자르면
캐릭터 안쪽의 비슷한 색(청바지 등)까지 뚫려 구멍이 생긴다.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

KEY = (255, 0, 255)  # 배경 표시용. 캐릭터에 없는 색이어야 한다


def remove_background(
    src: Path | str,
    dst: Path | str,
    thresh: int = 56,
    feather: float = 1.2,
) -> tuple[int, float]:
    """배경을 지우고 RGBA PNG 로 저장한다.

    반환값: (투명해진 픽셀 수, 전체 대비 비율)
    비율이 너무 낮으면 배경이 안 잘린 것이고, 너무 높으면 캐릭터까지 먹은 것이다.
    """
    im = Image.open(src).convert("RGB")
    w, h = im.size

    work = im.copy()
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
               (w // 2, 0), (w // 2, h - 1)):
        ImageDraw.floodfill(work, xy, KEY, thresh=thresh)

    # KEY 로 칠해진 곳 = 배경
    mask = Image.new("L", (w, h), 255)
    mpx, wpx = mask.load(), work.load()
    cleared = 0
    for y in range(h):
        for x in range(w):
            if wpx[x, y] == KEY:
                mpx[x, y] = 0
                cleared += 1

    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))

    out = im.convert("RGBA")
    out.putalpha(mask)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)
    return cleared, cleared / (w * h)


def sample_key(src: Path | str, patch: int = 24) -> tuple[int, int, int]:
    """네 모서리에서 배경색을 직접 잰다.

    생성 모델은 "#FF00FF" 라고 시켜도 정확히 그 값을 내지 않는다. JPEG 압축까지 거치면
    더 벌어진다. 가정하지 말고 실제 값을 읽는다.
    """
    im = Image.open(src).convert("RGB")
    w, h = im.size
    px = im.load()
    vals = []
    for ox, oy in ((0, 0), (w - patch, 0), (0, h - patch), (w - patch, h - patch)):
        for x in range(ox, ox + patch, 3):
            for y in range(oy, oy + patch, 3):
                vals.append(px[x, y])
    n = len(vals)
    return tuple(sorted(v[i] for v in vals)[n // 2] for i in range(3))  # 채널별 중앙값


def chroma_key(
    src: Path | str,
    dst: Path | str,
    key_rgb: tuple[int, int, int] | None = None,
    tolerance: int = 90,
    band: int = 60,
    despill: bool = True,
    feather: float = 1.0,
) -> tuple[float, tuple[int, int]]:
    """단색 배경(마젠타 등)을 색 거리로 지운다.

    flood fill 과 달리 **연결성을 보지 않는다.** 캐릭터에 없는 색을 배경으로 썼을 때만
    쓸 수 있고, 그 대신 머리카락처럼 배경과 밝기가 비슷한 부분도 안전하다.

    despill: 배경색이 캐릭터 가장자리에 번진 것(스필)을 걷어낸다.
    """
    if key_rgb is None:
        key_rgb = sample_key(src)
    im = Image.open(src).convert("RGB")
    w, h = im.size
    kr, kg, kb = key_rgb

    px = im.load()
    mask = Image.new("L", (w, h), 255)
    mpx = mask.load()
    cleared = 0

    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            dist = abs(r - kr) + abs(g - kg) + abs(b - kb)
            if dist < tolerance:
                mpx[x, y] = 0
                cleared += 1
            elif dist < tolerance + band:
                # 경계만 부드럽게. 폭을 고정하지 않으면 허용치를 올릴 때
                # 캐릭터 전체가 반투명해진다.
                mpx[x, y] = int(255 * (dist - tolerance) / band)

    if despill:
        # 번짐은 **경계에만** 생긴다. 안쪽까지 건드리면 볼 홍조·살색 그림자처럼
        # 원래 분홍인 부분을 잿빛으로 만든다.
        for y in range(h):
            for x in range(w):
                alpha = mpx[x, y]
                if alpha == 0 or alpha == 255:
                    continue                     # 완전 투명·완전 불투명은 건너뛴다
                r, g, b = px[x, y]
                if r > g and b > g:
                    m = (r + b) // 2
                    if m - g > 40:
                        px[x, y] = (min(r, g + 40), g, min(b, g + 40))

    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))

    out = im.convert("RGBA")
    out.putalpha(mask)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    out.save(dst)
    return cleared / (w * h), (w, h)


def split_sheet(
    src: Path | str,
    out_dir: Path | str,
    names: list[str],
    min_width: int = 60,
    alpha_floor: int = 16,
    pad: int = 10,
) -> list[Path]:
    """캐릭터 시트(여러 자세가 한 장)를 자세별 파일로 나눈다.

    배경이 제거된 RGBA 를 받아, **완전히 투명한 세로줄**을 경계로 삼는다.
    좌표를 눈대중으로 넣으면 다음에 시트를 다시 뽑을 때 또 손대야 한다.
    """
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    a = im.getchannel("A").load()

    filled = []
    for x in range(w):
        hit = False
        for y in range(0, h, 3):          # 3줄 간격으로 훑어도 충분하다
            if a[x, y] > alpha_floor:
                hit = True
                break
        filled.append(hit)

    segments, start = [], None
    for x, on in enumerate(filled):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start >= min_width:
                segments.append((start, x))
            start = None
    if start is not None and w - start >= min_width:
        segments.append((start, w))

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    for i, (x0, x1) in enumerate(segments):
        name = names[i] if i < len(names) else f"pose_{i + 1}"
        piece = im.crop((max(0, x0 - pad), 0, min(w, x1 + pad), h))
        box = piece.getbbox()
        if box:
            piece = piece.crop(box)
        p = out_dir / f"{name}.png"
        piece.save(p)
        made.append(p)
    return made


def trim(src: Path | str, dst: Path | str, pad: int = 8) -> tuple[int, int]:
    """투명 여백을 잘라내 캐릭터만 남긴다. 배치 계산이 쉬워진다."""
    im = Image.open(src).convert("RGBA")
    box = im.getbbox()
    if box:
        x0, y0, x1, y1 = box
        box = (max(0, x0 - pad), max(0, y0 - pad),
               min(im.width, x1 + pad), min(im.height, y1 + pad))
        im = im.crop(box)
    im.save(dst)
    return im.size
