#!/usr/bin/env python3
"""Generate every icon the Android build and the Play listing need.

There is no design file to export from, so the marks are drawn here from the
same tokens control.html uses. That keeps the app icon and the UI in sync: edit
GRAD or INK and everything downstream follows.

The mark is a V rendered as chunky LED cells, because the thing being
controlled is a 64x32 LED matrix — the icon shows what the product draws.

Outputs
  resources/            masters for @capacitor/assets to fan out into android/
  ../www/icons/         PWA icons for the browser-served /app page
  play/                 512 icon + 1024x500 feature graphic for the listing

Run:  python3 tools/make_icons.py      (from the app/ directory)
"""

import os
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(HERE)

# ── Brand tokens, lifted from control.html :root ──────────────────────
GRAD = [                       # 135deg sweep, stop positions match --grad
    (0.00, (0xFF, 0xC4, 0x6B)),   # --gold
    (0.38, (0xFF, 0x8A, 0x3D)),   # --warm
    (0.72, (0xFF, 0x4D, 0x2E)),   # --hot
    (1.00, (0xD8, 0x1F, 0x3C)),   # --deep
]
INK = (0x3D, 0x1A, 0x08)       # --on-grad. Dark on bright, per the CSS note:
                               # white only reaches 1.6:1 at the gold end.
BG = (0xF6, 0xF2, 0xF0)        # --bg
BG_DARK = (0x1A, 0x10, 0x0C)

# The V, on a 9x9 cell grid with a 2-cell stroke so it survives a 48px mdpi
# launcher. Anything thinner turns to mush at that size.
V_ROWS = [
    "XX.....XX",
    "XX.....XX",
    "XX.....XX",
    ".XX...XX.",
    ".XX...XX.",
    "..XX.XX..",
    "..XX.XX..",
    "...XXX...",
    "...XXX...",
]
GRID = len(V_ROWS)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def sample(t):
    """Colour at position t (0..1) along the gradient."""
    t = max(0.0, min(1.0, t))
    for i in range(len(GRAD) - 1):
        p0, c0 = GRAD[i]
        p1, c1 = GRAD[i + 1]
        if t <= p1:
            span = p1 - p0
            return lerp(c0, c1, 0.0 if span == 0 else (t - p0) / span)
    return GRAD[-1][1]


def gradient(size):
    """135deg linear gradient — top-left to bottom-right, as in CSS."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            px[x, y] = sample((x + y) / (2 * (size - 1)))
    return img


def rounded_mask(size, radius_frac=0.2237):
    """0.2237 is the iOS/Android squircle-ish corner ratio; it reads correctly
    whether or not the launcher applies its own mask."""
    m = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [0, 0, size * 4 - 1, size * 4 - 1],
        radius=int(size * 4 * radius_frac), fill=255)
    return m.resize((size, size), Image.LANCZOS)


def draw_v(size, coverage, colour=INK):
    """The V mark on a transparent canvas, occupying `coverage` of the width."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ss = 4                                  # supersample for clean cell edges
    big = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)

    span = size * ss * coverage
    cell = span / GRID
    gap = cell * 0.14                       # the dark seam between LED cells
    x0 = (size * ss - span) / 2
    y0 = (size * ss - span) / 2
    r = max(1, int(cell * 0.16))

    for row, line in enumerate(V_ROWS):
        for col, ch in enumerate(line):
            if ch != "X":
                continue
            left = x0 + col * cell + gap / 2
            top = y0 + row * cell + gap / 2
            d.rounded_rectangle(
                [left, top, left + cell - gap, top + cell - gap],
                radius=r, fill=colour + (255,))

    return Image.alpha_composite(img, big.resize((size, size), Image.LANCZOS))


def icon(size, rounded=True):
    """Full app icon: gradient tile, V knocked into it, soft inner glow."""
    base = gradient(size).convert("RGBA")

    # A faint light bloom from the top-left, so the tile reads as lit glass
    # rather than flat colour — the same trick body::before pulls in the CSS.
    glow = Image.new("L", (size, size), 0)
    ImageDraw.Draw(glow).ellipse(
        [-size * 0.35, -size * 0.45, size * 0.75, size * 0.55], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.13))
    base = Image.composite(Image.new("RGBA", (size, size), (255, 255, 255, 255)),
                           base, glow).convert("RGBA")

    base = Image.alpha_composite(base, draw_v(size, 0.60))
    if rounded:
        base.putalpha(rounded_mask(size))
    return base


def splash(size, dark=False):
    bg = BG_DARK if dark else BG
    img = Image.new("RGBA", (size, size), bg + (255,))
    tile = icon(int(size * 0.22))
    img.alpha_composite(tile, ((size - tile.width) // 2, (size - tile.height) // 2))
    return img


def feature_graphic():
    """1024x500 Play listing banner: gradient field, mark left, room for type."""
    w, h = 1024, 500
    g = gradient(w).resize((w, w), Image.LANCZOS).crop((0, (w - h) // 2, w, (w - h) // 2 + h))
    img = g.convert("RGBA")
    mark = draw_v(300, 0.72, colour=INK)
    img.alpha_composite(mark, (86, (h - 300) // 2))
    return img


def save(img, *parts):
    path = os.path.join(APP, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    print("  ", os.path.relpath(path, APP))


def main():
    print("masters for @capacitor/assets:")
    save(icon(1024), "resources", "icon.png")
    save(gradient(1024).convert("RGBA"), "resources", "icon-background.png")
    # Adaptive foreground: the launcher crops to the centre ~66/108 of the
    # canvas, so the mark has to sit well inside that or corners get clipped.
    save(draw_v(1024, 0.40), "resources", "icon-foreground.png")
    save(splash(2732), "resources", "splash.png")
    save(splash(2732, dark=True), "resources", "splash-dark.png")

    print("PWA icons:")
    save(icon(192), "www", "icons", "icon-192.png")
    save(icon(512), "www", "icons", "icon-512.png")
    # Maskable needs full-bleed art with the mark inside the 80% safe circle.
    save(icon(512, rounded=False), "www", "icons", "maskable-512.png")
    save(icon(180), "www", "icons", "apple-touch-icon.png")
    save(icon(32), "www", "icons", "favicon-32.png")

    print("Play Store listing:")
    save(icon(512, rounded=False), "play", "icon-512.png")
    save(feature_graphic(), "play", "feature-graphic-1024x500.png")


if __name__ == "__main__":
    main()
