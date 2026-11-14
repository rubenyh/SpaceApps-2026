"""Preview for judges. Pure: render() builds a new image every frame and never draws on the input,
so nothing can accumulate between frames. Text is drawn with a TTF font after any mirroring."""

from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Semantic colours (RGB): green normal, amber near threshold, red over threshold. Nothing else is coloured.
GREEN, AMBER, RED = (72, 199, 116), (255, 183, 47), (239, 83, 80)
WHITE, MUTED, TRACK, BG = (240, 242, 245), (150, 157, 168), (52, 58, 68), (16, 19, 24)
H, PANEL_W, M = 720, 480, 28


@dataclass
class Row:
    label: str
    value: str
    color: tuple = WHITE
    bar: float | None = None  # fill 0-1
    mark: float | None = None  # threshold position 0-1


@dataclass
class Notice:
    """Large message centred over the video (calibration, face lost)."""

    title: str
    subtitle: str
    color: tuple = WHITE
    progress: float | None = None


@lru_cache
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = ("segoeuib.ttf", "DejaVuSans-Bold.ttf") if bold else ("segoeui.ttf", "DejaVuSans.ttf")
    for name in names:
        for path in (f"C:/Windows/Fonts/{name}", name):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default(size)


def severity(value: float, mark: float, higher_is_worse: bool = True) -> tuple:
    """Red at/over the threshold, amber within 25 % of it, green otherwise."""
    if higher_is_worse:
        ratio = value / mark
    else:
        ratio = mark / value if value > 0 else float("inf")
    return RED if ratio >= 1 else AMBER if ratio >= 0.75 else GREEN


def render(
    frame_bgr: np.ndarray,
    title: str,
    status: str,
    sections: list[tuple[str, list[Row]]],
    footer: str,
    notice: Notice | None = None,
    points: list[tuple[float, float]] = (),
) -> np.ndarray:
    """Video scaled to 720 px high with a dark panel on its right. points: normalized landmark x, y."""
    h, w = frame_bgr.shape[:2]
    vw = round(w * H / h)
    video = cv2.cvtColor(cv2.resize(frame_bgr, (vw, H)), cv2.COLOR_BGR2RGB)
    for x, y in points:
        cv2.circle(video, (int(x * vw), int(y * H)), 2, (200, 230, 255), -1, cv2.LINE_AA)
    canvas = np.empty((H, vw + PANEL_W, 3), np.uint8)
    canvas[:, :vw] = video
    canvas[:, vw:] = BG

    if notice:
        bw, bh = min(vw - 2 * M, 760), 170
        bx, by = (vw - bw) // 2, H - bh - M  # bottom of the video: keeps the face visible
        box = canvas[by:by + bh, bx:bx + bw]
        canvas[by:by + bh, bx:bx + bw] = (box * 0.3 + np.array(BG) * 0.7).astype(np.uint8)

    img = Image.fromarray(canvas)
    d = ImageDraw.Draw(img)

    if notice:
        cx = bx + bw // 2
        d.text((cx, by + 22), notice.title, font=font(40, True), fill=notice.color, anchor="ma")
        d.text((cx, by + 80), notice.subtitle, font=font(24), fill=WHITE, anchor="ma")
        if notice.progress is not None:
            _bar(d, bx + 40, by + 128, bx + bw - 40, 14, notice.progress, GREEN)

    x0, x1 = vw + M, vw + PANEL_W - M
    y = M
    d.text((x0, y), title, font=font(30, True), fill=WHITE)
    y += 46
    d.text((x0, y), status, font=font(26, True), fill=WHITE)
    y += 48
    d.line((x0, y, x1, y), fill=TRACK, width=2)
    y += 18
    for header, rows in sections:
        d.text((x0, y), header, font=font(20, True), fill=MUTED)
        y += 32
        for r in rows:
            d.text((x0, y), r.label, font=font(24), fill=WHITE)
            d.text((x1, y), r.value, font=font(24, True), fill=r.color, anchor="ra")
            y += 36
            if r.bar is not None:
                _bar(d, x0, y, x1, 8, r.bar, r.color, r.mark)
                y += 20
            else:
                y += 6
        y += 14
    d.text((x0, H - M), footer, font=font(18), fill=MUTED, anchor="ld")
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def _bar(d: ImageDraw.ImageDraw, x0: int, y: int, x1: int, height: int, fill: float, color: tuple,
         mark: float | None = None) -> None:
    clamp = lambda v: min(max(v, 0.0), 1.0)  # noqa: E731
    d.rounded_rectangle((x0, y, x1, y + height), radius=height // 2, fill=TRACK)
    if fill > 0:
        d.rounded_rectangle((x0, y, x0 + max(height, (x1 - x0) * clamp(fill)), y + height),
                            radius=height // 2, fill=color)
    if mark is not None:
        mx = x0 + (x1 - x0) * clamp(mark)
        d.line((mx, y - 4, mx, y + height + 4), fill=WHITE, width=2)
