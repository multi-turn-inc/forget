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
SCALE = 8
W, H = 96, 44


def _dab(draw: ImageDraw.ImageDraw, x: float, y: float, radius: float) -> None:
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=RED)


def _erase(image: Image.Image, points: list[tuple[float, float, float]], gap: float) -> None:
    """Punch a transparent casing along a path — the under-strand breaks
    where the over-strand passes, which is what makes it read as a braid."""
    from PIL import ImageChops

    eraser = Image.new("L", image.size, 0)
    edraw = ImageDraw.Draw(eraser)
    for x, y, radius in points:
        r = radius + gap
        edraw.ellipse([x - r, y - r, x + r, y + r], fill=255)
    alpha = ImageChops.subtract(image.getchannel("A"), eraser)
    image.putalpha(alpha)


def draw_gear(lobes: int, phase: float = 0.0) -> Image.Image:
    width, height = W * SCALE, H * SCALE
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    center = height / 2
    margin = 7 * SCALE
    span = width - 2 * margin
    amplitude_max = height * 0.315
    base_radius = 2.6 * SCALE

    samples = 720

    def path(sign: int) -> list[tuple[float, float, float]]:
        """(x, y, radius) — 굵기가 살아 있는 획: 마디 가운데 통통하고
        교차점·양끝에서 가늘어지는 캘리그래피 타입."""
        points = []
        for i in range(samples + 1):
            u = i / samples
            x = margin + span * u
            theta = math.pi * lobes * u + phase
            envelope = math.sin(math.pi * u) ** 0.32 if lobes else 0.0
            # 유기적 비대칭: 마디마다 진폭이 미세하게 다름
            wobble = 1.0 + 0.10 * math.sin(2.1 * math.pi * u + sign * 0.7)
            y = center + sign * amplitude_max * envelope * wobble * math.sin(theta)
            if lobes:
                belly = abs(math.sin(theta)) ** 0.9
                # 교차점에서도 실이 살아 있어야 땋임이 읽힌다 — 최소 굵기 65%
                radius = base_radius * (0.65 + 0.35 * belly * envelope)
            else:
                # low: 곧은 실도 죽은 직선이 아니라 숨 쉬는 획으로
                y = center + 1.1 * SCALE * math.sin(math.pi * u * 2) * math.sin(math.pi * u)
                radius = base_radius * (0.55 + 0.40 * math.sin(math.pi * u) ** 0.8)
            points.append((x, y, radius))
        return points

    if not lobes:
        draw = ImageDraw.Draw(image)
        for x, y, radius in path(0):
            _dab(draw, x, y, radius)
        return image.resize((W, H), Image.LANCZOS)

    strand_a, strand_b = path(1), path(-1)
    # 마디 경계 = 꼭대기(apex), 교차점은 마디 한가운데 — 둘 다 위상에서
    # 동적으로 푼다 (θ = πku + φ; apex: θ≡π/2, crossing: θ≡0 (mod π)).
    def u_solutions(offset: float) -> list[float]:
        out = []
        n = math.floor(phase / math.pi) - 1
        while True:
            u = (offset + n * math.pi - phase) / (math.pi * lobes)
            if u >= 1:
                break
            if 0 < u < 1:
                out.append(u)
            n += 1
        return out

    apex_us = u_solutions(math.pi / 2)
    bounds = [0, *[int(u * samples) for u in apex_us], samples]
    def crossing_parity(lo: int, hi: int) -> int | None:
        mid_u_lo, mid_u_hi = lo / samples, hi / samples
        n = math.floor(phase / math.pi) - 1
        while True:
            u = (n * math.pi - phase) / (math.pi * lobes)
            if u >= mid_u_hi:
                return None
            if mid_u_lo < u < mid_u_hi:
                return n % 2
            n += 1

    segments = []  # (points, is_over)
    for k in range(len(bounds) - 1):
        lo, hi = bounds[k], bounds[k + 1] + 1
        parity = crossing_parity(bounds[k], bounds[k + 1])
        a_over = parity == 1
        b_over = parity == 0
        segments.append((strand_a[lo:hi], a_over))
        segments.append((strand_b[lo:hi], b_over))

    draw = ImageDraw.Draw(image)
    # 1) 아래로 지나가는 마디들 먼저
    for points, over in segments:
        if not over:
            for x, y, radius in points:
                _dab(draw, x, y, radius)
    # 2) 위로 지나가는 마디: 아래 실을 끊고(케이싱) 그 위에 얹기
    gap = 1.8 * SCALE
    for points, over in segments:
        if over:
            _erase(image, points, gap)
    draw = ImageDraw.Draw(image)
    for points, over in segments:
        if over:
            for x, y, radius in points:
                _dab(draw, x, y, radius)
    # 3) 양끝 꼬리: 한 가닥으로 모여 뾰족하게 맺힘
    for x0, x1, tip in ((margin, 1 * SCALE, True), (width - margin, width - 1 * SCALE, True)):
        steps = 40
        for i in range(steps + 1):
            u = i / steps
            x = x0 + (x1 - x0) * u
            radius = base_radius * 0.52 * (1.0 - 0.75 * u)
            _dab(draw, x, center, radius)
    return image.resize((W, H), Image.LANCZOS)


FRAMES = 6


def main() -> None:
    out_dir = os.path.expanduser("~/.forget/menubar-icons")
    os.makedirs(out_dir, exist_ok=True)
    for gear, lobes in GEARS.items():
        path = os.path.join(out_dir, f"gear-{gear}.png")
        draw_gear(lobes).save(path)
        print(path)
        if lobes:
            # 동작 중 애니메이션: 위상이 흘러 실이 감기는 6프레임
            for j in range(FRAMES):
                frame = draw_gear(lobes, phase=math.pi * j / FRAMES)
                frame.save(os.path.join(out_dir, f"gear-{gear}-f{j}.png"))


if __name__ == "__main__":
    main()
