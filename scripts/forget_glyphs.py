#!/usr/bin/env python3
"""Menu bar glyphs: the brand's red thread, twisted by recall intensity.

The dial as a picture — a straight thread barely remembers; a tight braid
is deep recall. One glyph per gear (low=straight, medium=1 twist,
high=2, extra=3), horizontal, brand red #d31126, transparent background.

Writes ~/.forget/menubar-icons/gear-<gear>.png (96×44 @2x → 48×22pt).
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw

RED = (211, 17, 38, 255)  # --red from forget.sh
GEARS = {"low": 0, "medium": 1, "high": 2, "extra": 3}
SCALE = 4
W, H = 96, 44
STROKE = 5.2


def draw_gear(lobes: int) -> Image.Image:
    width, height = W * SCALE, H * SCALE
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    center = height / 2
    margin = 6 * SCALE
    span = width - 2 * margin
    amplitude_max = height * 0.30
    stroke = STROKE * SCALE / 2

    def strand(sign: int) -> list[tuple[float, float]]:
        points = []
        for i in range(241):
            u = i / 240
            x = margin + span * u
            envelope = math.sin(math.pi * u) ** 0.45 if lobes else 0.0
            y = center + sign * amplitude_max * envelope * math.sin(math.pi * lobes * u)
            points.append((x, y))
        return points

    for sign in (1, -1) if lobes else (0,):
        points = strand(sign)
        for a, b in zip(points, points[1:]):
            draw.line([a, b], fill=RED, width=int(stroke * 2))
        for x, y in points[:: 24]:
            draw.ellipse([x - stroke, y - stroke, x + stroke, y + stroke], fill=RED)
    # 양끝 꼬리: 한 가닥으로 이어지는 진입/진출 실
    for x0, x1 in ((0, margin), (width - margin, width)):
        draw.line([(x0, center), (x1, center)], fill=RED, width=int(stroke * 2))
    return image.resize((W, H), Image.LANCZOS)


def main() -> None:
    out_dir = os.path.expanduser("~/.forget/menubar-icons")
    os.makedirs(out_dir, exist_ok=True)
    for gear, lobes in GEARS.items():
        path = os.path.join(out_dir, f"gear-{gear}.png")
        draw_gear(lobes).save(path)
        print(path)


if __name__ == "__main__":
    main()
