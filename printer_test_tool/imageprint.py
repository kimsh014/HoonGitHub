# -*- coding: utf-8 -*-
"""이미지 파일(JPG/PNG/BMP/GIF) → 감열 프린터용 흑백 래스터.

  1. EXIF 회전 보정, 투명 배경은 흰색으로
  2. 인쇄 폭(dots) x 너비 % 로 축소 (확대는 하지 않음)
  3. 밝기·대비 조정 후 흑백 변환: 사진 = 디더링(점 밀도로 회색 표현), 로고·글자 = 단순 흑백
  4. 정렬에 맞춰 인쇄 폭 전체 캔버스에 붙여서 GS v 0 (24행씩) 로 보낸다
"""
from PIL import Image, ImageEnhance, ImageOps

from escpos import DOT_MM, Receipt

FILETYPES = [("이미지", "*.jpg *.jpeg *.png *.bmp *.gif"), ("모든 파일", "*.*")]
MODES = {"photo": "사진 (디더링)", "logo": "로고·글자 (흑백)"}
ALIGNS = {"center": "가운데", "left": "왼쪽", "right": "오른쪽"}
MAX_ROWS = 8000          # 약 1m. 실수로 아주 긴 이미지를 보내 용지를 다 쓰는 것을 막는다


def load(path):
    """파일을 열어 회전 보정 + 흰 배경 RGB 로. 열 수 없으면 OSError/ValueError."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, im)
        return im.convert("RGB")


def convert(src, dots=576, width_pct=100, mode="photo", brightness=0, contrast=0, align="center"):
    """RGB 이미지 → 인쇄 폭 전체의 1비트 이미지 (mode '1', 0 = 검정 = 인쇄).

    brightness/contrast: -50 ~ +50 (%). 반환 이미지의 높이는 MAX_ROWS 로 잘린다.
    """
    w = max(8, int(dots * max(10, min(100, width_pct)) / 100))
    w = min(w, src.width)                       # 작은 이미지는 키우지 않는다 (계단 현상)
    h = max(1, round(src.height * w / src.width))
    g = src.convert("L").resize((w, h), Image.Resampling.LANCZOS)
    if brightness:
        g = ImageEnhance.Brightness(g).enhance(1 + brightness / 100)
    if contrast:
        g = ImageEnhance.Contrast(g).enhance(1 + contrast / 100)
    if mode == "logo":
        bw = g.point(lambda p: 255 if p >= 128 else 0).convert("1", dither=Image.Dither.NONE)
    else:
        bw = g.convert("1")                     # Floyd-Steinberg 디더링
    bw = bw.crop((0, 0, w, min(h, MAX_ROWS)))
    canvas = Image.new("1", (dots, bw.height), 1)
    x = {"left": 0, "right": dots - w}.get(align, (dots - w) // 2)
    canvas.paste(bw, (x, 0))
    canvas.info.update(img_w=w, full_h=h)
    return canvas


def to_escpos(bw, opts=None, cut="partial", feed_lines=3):
    """1비트 이미지 → ESC/POS 바이트 (초기화 + 래스터 + 급지 + 컷)."""
    o = opts or {}
    r = Receipt(o.get("encoding", "cp949"), o.get("korean_mode", True), bw.width).init()
    # PIL '1' 의 tobytes 는 행마다 MSB 부터 8픽셀씩, 1 = 흰색 → 프린터는 1 = 검정이라 뒤집는다
    data = bytes(b ^ 0xFF for b in bw.tobytes())
    r.raster_packed((bw.width + 7) // 8, bw.height, data)
    r.feed(feed_lines)
    if cut == "full":
        r.cut(partial=False)
    elif cut == "partial":
        r.cut(partial=True)
    return r.bytes()


def info(src, bw):
    """미리보기 아래에 보여줄 설명."""
    w = bw.info.get("img_w", bw.width)
    cut = " — 너무 길어 약 1m 에서 잘립니다" if bw.info.get("full_h", 0) > bw.height else ""
    return (f"원본 {src.width}×{src.height}px → 인쇄 {w}×{bw.height}도트 "
            f"(약 {w * DOT_MM:.0f}×{bw.height * DOT_MM:.0f}mm){cut}")
