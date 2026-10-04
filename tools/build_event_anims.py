"""Draw the event animations in code and write them as .bin clips for the screen.

    python3 tools/build_event_anims.py            # all of them
    python3 tools/build_event_anims.py halloween  # just one

Writes anims/<name>.bin (the LDA1 format device_app.py plays, 10 frames a
second) and anims/previews/<name>.gif, an enlarged copy to look at on a
laptop. The four event clips loop seamlessly; news_intro is a one-shot that
ends on the news screen's own header so the story can follow straight on.
"""

import math
import os
import random
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "sim"))
sys.path.insert(0, ROOT)

import fakehw  # noqa: E402

fakehw.install()
from device_app import FONT_3X5, FONT_BOLD_5X5  # noqa: E402  (the screen's own fonts)
from mp4_to_anim import build_anim_bytes  # noqa: E402

W, H = 64, 32
TAU = math.pi * 2


# ---------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------
def lerp(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def scale(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def rnd(i, salt=0):
    return random.Random(i * 7919 + salt * 104729).random()


class Canvas:
    def __init__(self, top=(0, 0, 0), bottom=None):
        self.im = Image.new("RGB", (W, H), top)
        self.p = self.im.load()
        if bottom is not None:
            for y in range(H):
                c = lerp(top, bottom, y / (H - 1))
                for x in range(W):
                    self.p[x, y] = c

    def px(self, x, y, c):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < W and 0 <= y < H:
            self.p[x, y] = c

    def add(self, x, y, c, a=1.0):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < W and 0 <= y < H:
            o = self.p[x, y]
            self.p[x, y] = tuple(min(255, int(o[i] + c[i] * a)) for i in range(3))

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.px(xx, yy, c)

    def disc(self, cx, cy, r, c):
        for y in range(int(cy - r - 1), int(cy + r + 2)):
            for x in range(int(cx - r - 1), int(cx + r + 2)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r + 0.5:
                    self.px(x, y, c)

    def glow(self, cx, cy, r, c, strength=1.0):
        for y in range(int(cy - r), int(cy + r + 1)):
            for x in range(int(cx - r), int(cx + r + 1)):
                d = math.hypot(x - cx, y - cy) / r
                if d < 1:
                    self.add(x, y, c, strength * (1 - d) ** 2)

    def sprite(self, rows, x, y, cmap):
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch in cmap:
                    self.px(x + c, y + r, cmap[ch])

    def text(self, s, x, y, color, font=FONT_3X5, spacing=1):
        """color is an (r,g,b) or a function (px_x, px_y) -> (r,g,b)."""
        cx = x
        for ch in s.upper():
            grid = font.get(ch)
            if not grid:
                cx += 3 + spacing
                continue
            for r, row in enumerate(grid):
                for c, pix in enumerate(row):
                    if pix != " ":
                        self.px(cx + c, y + r, color(cx + c, y + r) if callable(color) else color)
            cx += len(grid[0]) + spacing


def text_w(s, font, spacing=1):
    return sum(len(font[ch][0]) + spacing if ch in font else 3 + spacing for ch in s.upper()) - spacing


def falling(n, f, N, salt, loops=(1, 2), sway=2.0):
    """n particles that fall and wrap, landing back where they started after N frames."""
    for i in range(n):
        k = loops[i % len(loops)]
        t = (rnd(i, salt) + k * f / N) % 1.0
        x = rnd(i, salt + 1) * W + sway * math.sin(TAU * (f / N * (1 + i % 2) + rnd(i, salt + 2)))
        yield i, x, t * (H + 8) - 4


# ---------------------------------------------------------------------
# Canadian Thanksgiving
# ---------------------------------------------------------------------
MAPLE = [
    ".......#.......",
    "......###......",
    ".#....###....#.",
    ".##.#######.##.",
    "..###########..",
    "#.###########.#",
    "###############",
    ".#############.",
    "..###########..",
    "...#########...",
    "..###########..",
    ".###..###..###.",
    ".......#.......",
    ".......#.......",
    ".......#.......",
]
LEAF_COLS = [(255, 60, 20), (255, 140, 0), (255, 200, 40), (200, 40, 10), (230, 100, 10)]
SMALL_LEAF = [[".#.", "###", ".#."], ["#.", "##"], ["##", ".#"]]


def thanksgiving(f, N):
    c = Canvas((46, 16, 0), (10, 2, 0))
    for i, x, y in falling(7, f, N, salt=11, loops=(1,)):          # behind the leaf
        c.sprite(SMALL_LEAF[i % 3], int(x), int(y), {"#": scale(LEAF_COLS[i % 5], 0.45)})
    breathe = 0.85 + 0.15 * math.sin(TAU * f / N)
    c.glow(11, 15, 14, (120, 30, 0), 0.5 * breathe)
    c.sprite(MAPLE, 4, 8 + round(math.sin(TAU * f / N)), {"#": scale((255, 30, 20), breathe)})
    for i, x, y in falling(6, f, N, salt=23, loops=(2, 1)):          # in front
        c.sprite(SMALL_LEAF[(i + 1) % 3], int(x), int(y), {"#": LEAF_COLS[(i + 2) % 5]})
    cream = (255, 235, 190)                                           # words stay readable on top
    c.text("HAPPY", 27 + (35 - text_w("HAPPY", FONT_3X5)) // 2, 6, (255, 170, 40))
    c.text("THANKS", 27 + (35 - text_w("THANKS", FONT_3X5)) // 2, 14, cream)
    c.text("GIVING", 27 + (35 - text_w("GIVING", FONT_3X5)) // 2, 21, cream)
    return c.im


# ---------------------------------------------------------------------
# Halloween
# ---------------------------------------------------------------------
PUMPKIN = [
    ".......gg......",
    "......gg.......",
    "...ooodooodoo..",
    ".oodooodooodoo.",
    "oodoEoodooEodoo",
    "oodEEEodoEEEdoo",
    "oodooodooodoooo",
    "ooEoEoEoEoEoEoo",
    "oodEEEEEEEEEdoo",
    ".oodEoEoEoEdoo.",
    "..odooodooodo..",
    "....ooodooo....",
]
GHOST = [
    "..wwwww..",
    ".wwwwwww.",
    "wwwwwwwww",
    "wwkwwwkww",
    "wwkwwwkww",
    "wwwwwwwww",
    "wwwwkwwww",
    "wwwwwwwww",
    "wwwwwwwww",
]
GHOST_HEM = ["w.ww.ww.w", "ww.ww.ww."]
BAT = [["#.....#", "##.#.##", ".#####.", "..#.#.."],
       [".......", ".##.##.", "#######", "#.#.#.#"]]
TOMB = [".#####.", "#######", "###.###", "##...##", "###.###", "###.###", "#######", "#######"]


def halloween(f, N):
    c = Canvas((30, 0, 55), (8, 0, 20))
    for i in range(10):                                               # stars
        tw = 0.5 + 0.5 * math.sin(TAU * (f / N * (1 + i % 3) + rnd(i, 5)))
        c.px(rnd(i, 6) * W, rnd(i, 7) * 15, scale((200, 190, 255), 0.25 + 0.6 * tw))
    c.glow(52, 8, 12, (90, 80, 30), 0.6)
    c.disc(52, 8, 6, (255, 238, 170))
    for dx, dy in ((-2, -2), (2, 1), (-1, 3)):
        c.px(52 + dx, 8 + dy, (215, 195, 130))
    c.rect(0, 30, W, 2, (10, 28, 12))
    c.sprite(TOMB, 53, 22, {"#": (70, 70, 90), ".": (25, 20, 35)})
    for i in range(2):                                                # bats
        t = (rnd(i, 9) + f / N) % 1.0
        x = t * (W + 14) - 7 if i == 0 else (1 - t) * (W + 14) - 7
        y = 4 + 9 * i + 2 * math.sin(TAU * (2 * f / N + i * 0.4))
        c.sprite(BAT[(f // 2 + i) % 2], int(x), int(y), {"#": (5, 0, 10)})
    flick = 0.75 + 0.25 * math.sin(TAU * 5 * f / N) * math.sin(TAU * 3 * f / N + 1)
    c.glow(10, 24, 12, (150, 60, 0), 0.5 * flick)
    c.sprite(PUMPKIN, 3, 18, {"o": (255, 110, 0), "d": (200, 70, 0), "g": (40, 150, 30),
                              "E": scale((255, 230, 60), flick)})
    gy = 11 + round(2 * math.sin(TAU * f / N))
    gx = 30 + round(2 * math.sin(TAU * f / N + 1.3))
    white = (235, 240, 255)
    c.glow(gx + 4, gy + 5, 9, (60, 60, 110), 0.5)
    c.sprite(GHOST + [GHOST_HEM[(f // 3) % 2]], gx, gy, {"w": white, "k": (15, 0, 30)})
    return c.im


# ---------------------------------------------------------------------
# Christmas
# ---------------------------------------------------------------------
XMAS_LIGHTS = [(255, 40, 40), (255, 200, 40), (60, 140, 255), (255, 80, 200), (255, 255, 255)]


def tree_half_width(y):
    """Three stacked tiers between y=5 and y=25."""
    if not 5 <= y <= 25:
        return -1
    tier, row = divmod(y - 5, 7)
    return 1 + row + tier * 1.5


def christmas(f, N):
    c = Canvas((0, 8, 40), (0, 0, 14))
    for i, x, y in falling(8, f, N, salt=31, loops=(1,), sway=1.5):      # far snow
        c.px(x, y, (90, 110, 160))
    for x in range(W):                                                    # snowy ground
        top = 28 + (1 if (x // 9) % 2 else 0)
        for y in range(top, H):
            c.px(x, y, (215, 230, 255) if y == top else (170, 195, 240))
    cx = 13
    c.rect(cx - 1, 26, 3, 3, (110, 60, 20))
    for y in range(5, 26):
        hw = int(tree_half_width(y))
        for x in range(cx - hw, cx + hw + 1):
            edge = abs(x - cx) == hw
            c.px(x, y, (0, 95, 35) if edge else (0, 150, 50))
    for i in range(12):                                                   # fairy lights
        y = 8 + int(rnd(i, 41) * 17)
        hw = int(tree_half_width(y)) - 1
        x = cx + int((rnd(i, 42) * 2 - 1) * max(hw, 0))
        tw = 0.5 + 0.5 * math.sin(TAU * (2 * f / N + rnd(i, 43)))
        col = XMAS_LIGHTS[(i + (f * 5 // N)) % 5]
        c.px(x, y, scale(col, 0.35 + 0.65 * tw))
    pulse = 0.7 + 0.3 * math.sin(TAU * 3 * f / N)
    c.glow(cx, 4, 5, (120, 100, 20), 0.6 * pulse)
    for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
        c.px(cx + dx, 4 + dy, scale((255, 220, 60), pulse))
    c.rect(22, 24, 5, 4, (220, 30, 40)); c.rect(24, 24, 1, 4, (255, 220, 60))   # presents
    c.rect(2, 25, 4, 3, (40, 110, 255)); c.rect(3, 25, 1, 3, (255, 255, 255))
    sweep = (f / N) * 60 - 10                                             # a glint crossing the words

    def tint(base):
        return lambda x, y: lerp(base, (255, 255, 255), 1 - abs((x - 30) + (y - 8) * 0.5 - sweep) / 3)

    c.text("MERRY", 31, 8, tint((255, 45, 45)), font=FONT_BOLD_5X5)
    c.text("XMAS", 31 + (29 - text_w("XMAS", FONT_BOLD_5X5)) // 2, 16, tint((50, 220, 90)), font=FONT_BOLD_5X5)
    for i, x, y in falling(14, f, N, salt=37, loops=(2, 1, 3), sway=2.0):  # near snow
        c.px(x, y, (255, 255, 255))
    return c.im


# ---------------------------------------------------------------------
# Oh, Mary! on the West End
# ---------------------------------------------------------------------
CURTAIN = [(205, 15, 40), (160, 8, 28), (105, 2, 16), (160, 8, 28)]


def oh_mary(f, N):
    c = Canvas((30, 0, 26), (12, 0, 14))
    sx = 32 + 12 * math.sin(TAU * f / N)                                  # spotlight drifting
    c.glow(sx, 17, 20, (110, 20, 80), 0.9)
    for x in list(range(0, 9)) + list(range(55, 64)):                     # side curtains
        col = CURTAIN[(x if x < 32 else 63 - x) % 4]
        for y in range(H):
            c.px(x, y, scale(col, 1.0 - 0.012 * y))
    for x in range(W):                                                    # scalloped valance
        drop = 3 + (1 if (x % 8) in (3, 4) else 0)
        for y in range(drop + 1):
            c.px(x, y, CURTAIN[(x // 2) % 4])
        c.px(x, drop + 1, (255, 200, 60))
    x0, y0, x1, y1 = 11, 8, 52, 29                                        # marquee bulbs
    path = ([(x, y0) for x in range(x0, x1 + 1, 3)] + [(x1, y) for y in range(y0 + 3, y1, 3)]
            + [(x, y1) for x in range(x1, x0 - 1, -3)] + [(x0, y) for y in range(y1 - 3, y0, -3)])
    for i, (x, y) in enumerate(path):
        lit = (i - f // 2) % 3 == 0
        c.px(x, y, (255, 225, 90) if lit else (95, 60, 10))
        if lit:
            c.glow(x, y, 2.5, (120, 90, 20), 0.5)
    sweep = (f / N) * 70 - 15

    def pink(x, y):
        return lerp((255, 50, 160), (255, 255, 255), 1 - abs((x - 12) + (y - 12) * 0.6 - sweep) / 3)

    c.text("OH,", 32 - text_w("OH,", FONT_BOLD_5X5) // 2, 12, pink, font=FONT_BOLD_5X5)
    c.text("MARY!", 32 - text_w("MARY!", FONT_BOLD_5X5) // 2 + 1, 20, pink, font=FONT_BOLD_5X5)
    return c.im


# ---------------------------------------------------------------------
# Claude news intro (one-shot)
# ---------------------------------------------------------------------
CORAL = (232, 112, 72)
SPARK_RAYS = [(0, 1.0), (31, 0.78), (58, 0.95), (90, 0.82), (118, 1.0), (149, 0.8), (180, 0.97),
              (212, 0.8), (240, 1.0), (270, 0.84), (301, 0.96), (330, 0.8)]
NEWS_RED, NEWS_GREY = (255, 50, 50), (80, 80, 80)        # the news screen's own header colours
SS = 8                                                   # supersampling for the spark


def ease_out_back(t):
    t = max(0.0, min(1.0, t))
    return 1 + 2.4 * (t - 1) ** 3 + 1.4 * (t - 1) ** 2


def draw_spark(size, spin, squash, stretch, cy, color):
    big = Image.new("RGB", (W * SS, H * SS), (0, 0, 0))
    d = ImageDraw.Draw(big)
    cx, cyy = 32 * SS, cy * SS
    width = max(SS, int(1.9 * SS))
    for ang, length in SPARK_RAYS:
        a = math.radians(ang + spin)
        ex = cx + math.cos(a) * size * length * SS * stretch
        ey = cyy + math.sin(a) * size * length * SS * squash
        d.line([(cx, cyy), (ex, ey)], fill=color, width=width)
        d.ellipse([ex - width / 2, ey - width / 2, ex + width / 2, ey + width / 2], fill=color)
    return big.resize((W, H), Image.Resampling.BOX)


def news_intro(f, N):
    c = Canvas()
    if f <= 9:                                           # spark bursts open, then breathes
        size = 12.5 * ease_out_back(f / 5) * (1 + (0.04 * math.sin(TAU * (f - 5) / 5) if f > 5 else 0))
        c.im = draw_spark(size, spin=-40 + 4 * f, squash=1, stretch=1, cy=16, color=CORAL)
    elif f <= 13:                                        # flattens into a line across the screen
        t = (f - 9) / 4
        c.im = draw_spark(12.5, spin=0, squash=(1 - t) ** 2, stretch=1 + 2.2 * t, cy=16, color=CORAL)
        c.p = c.im.load()
        if f == 13:
            c.rect(0, 16, W, 1, CORAL)
    else:                                                # line rises to become the header rule
        t = min(1.0, (f - 13) / 4)
        y = round(16 - 9 * t)
        c.rect(0, y, W, 1, lerp(CORAL, NEWS_GREY, t))
        letters = min(4, f - 13)
        c.text("NEWS"[:letters], 1, 1, NEWS_RED)
    return c.im


ANIMS = {
    # name: (frame function, frames, palette size)
    "thanksgiving": (thanksgiving, 48, 96),
    "halloween": (halloween, 60, 128),
    "christmas": (christmas, 60, 128),
    "oh_mary": (oh_mary, 36, 128),
    "news_intro": (news_intro, 22, 64),
}


def build(name):
    fn, n, colors = ANIMS[name]
    frames = [fn(f, n).convert("RGB") for f in range(n)]
    out_dir = os.path.join(ROOT, "anims")
    os.makedirs(os.path.join(out_dir, "previews"), exist_ok=True)
    data = build_anim_bytes(frames, colors, dither=False)
    with open(os.path.join(out_dir, name + ".bin"), "wb") as fh:
        fh.write(data)
    big = [fr.resize((W * 10, H * 10), Image.Resampling.NEAREST) for fr in frames]
    big[0].save(os.path.join(out_dir, "previews", name + ".gif"), save_all=True,
                append_images=big[1:], duration=100, loop=0)
    print(f"{name}: {n} frames ({n / 10:.1f}s), {len(data) / 1024:.0f} KB")
    return frames


if __name__ == "__main__":
    for name in (sys.argv[1:] or ANIMS):
        build(name)
