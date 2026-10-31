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


def claude(f, N):
    """The news intro's spark on its own: one slow full turn with a gentle
    breath, so it loops forever without a seam."""
    c = Canvas()
    size = 12.5 * (1 + 0.06 * math.sin(TAU * 2 * f / N))
    c.im = draw_spark(size, spin=360 * f / N, squash=1, stretch=1, cy=16, color=CORAL)
    return c.im


# ---------------------------------------------------------------------
# Halloween party (dancing skeletons, bouncing pumpkin, disco floor)
# ---------------------------------------------------------------------
SKELETON = [
    ["..www..", ".wwwww.", ".wkwkw.", ".wwwww.", "..w.w..", "w..w..w", ".w.w.w.",
     "..www..", "...w...", "..www..", "...w...", "..w.w..", ".w...w.", ".w...w.", "ww...ww"],
    ["..www..", ".wwwww.", ".wkwkw.", ".wwwww.", "..w.w..", "...w...", ".wwwww.",
     "w.www.w", "w..w..w", "..www..", "...w...", "..w.w..", ".w...w.", "w.....w", "w.....w"],
]
PARTY_COLS = [(255, 110, 0), (120, 255, 40), (190, 60, 255), (255, 40, 120), (40, 200, 255)]


def halloween_party(f, N):
    beat = f // 5                                  # 120 bpm at 10 fps
    phase = (f % 5) / 5
    c = Canvas((26, 0, 44), (6, 0, 16))
    for i, (ox, oy, col) in enumerate(((0.0, 0.3, (120, 0, 160)), (0.5, 0.8, (0, 90, 60)))):
        gx = 32 + 26 * math.sin(TAU * (f / N + ox))
        gy = 18 + 6 * math.sin(TAU * (2 * f / N + oy))
        c.glow(gx, gy, 14, col, 0.55)
    for x in range(0, W, 8):                       # disco floor
        col = PARTY_COLS[(x // 8 + beat) % len(PARTY_COLS)]
        c.rect(x, 29, 8, 3, scale(col, 0.75 - 0.35 * phase))
        c.rect(x, 29, 1, 3, (10, 0, 20))
    for i in range(2):                             # bats
        t = (rnd(i, 21) + f / N) % 1.0
        x = t * (W + 14) - 7 if i == 0 else (1 - t) * (W + 14) - 7
        y = 9 + 3 * i + math.sin(TAU * (3 * f / N + i * 0.4))
        c.sprite(BAT[(f // 2 + i) % 2], int(x), int(y), {"#": (5, 0, 10)})
    bounce = round(2 * abs(math.sin(math.pi * phase)))
    bone = (240, 240, 225)
    for i, sx in enumerate((5, 52)):               # dancing skeletons
        pose = SKELETON[(beat + i) % 2]
        if i:
            pose = [r[::-1] for r in pose]
        c.sprite(pose, sx, 14 - bounce, {"w": bone, "k": (20, 0, 30)})
    flick = 0.75 + 0.25 * math.sin(TAU * 5 * f / N) * math.sin(TAU * 3 * f / N + 1)
    py = 16 - 2 * bounce
    c.glow(31, py + 6, 12, (160, 70, 0), 0.5 * flick)
    c.sprite(PUMPKIN, 24, py, {"o": (255, 110, 0), "d": (200, 70, 0), "g": (40, 150, 30),
                               "E": scale((255, 230, 60), flick)})
    word = "HALLOWEEN" if f < N // 2 else "PARTY!"
    x0 = (W - text_w(word, FONT_BOLD_5X5)) // 2
    cx = x0
    for k, ch in enumerate(word):                  # wavy rainbow letters
        y = 2 + round(1.4 * math.sin(TAU * (2 * f / N) + k * 0.7))
        col = PARTY_COLS[(k + beat) % len(PARTY_COLS)]
        c.text(ch, cx, y, col, font=FONT_BOLD_5X5)
        cx += text_w(ch, FONT_BOLD_5X5) + 1
    if f % (N // 2) in (0, 1):                     # lightning flash on the word change
        k = 0.7 if f % (N // 2) == 0 else 0.35
        c.im = Image.blend(c.im, Image.new("RGB", (W, H), (230, 230, 255)), k)
    return c.im


# ---------------------------------------------------------------------
# Halloween spooky (moonlit graveyard, fog, eyes, lightning, rising ghost)
# ---------------------------------------------------------------------
DEAD_TREE = [
    "#.....#.....",
    ".#...#...#..",
    "..#.#...#...",
    "...##..#..#.",
    "....#.#..#..",
    "....##..#...",
    ".....###....",
    ".....##.....",
    ".....##.....",
    ".....##.....",
    ".....##.....",
    ".....##.....",
    "....###.....",
    "....####....",
]
REAPER = [
    "...###...",
    "..#####..",
    ".##...##.",
    ".#.r.r.#.",
    ".##...##.",
    "#########",
    "#########",
    "#########",
    "#########",
    "#########",
    "#########",
    ".#######.",
    ".#.#.#.#.",
]
WISP = [
    "..www..",
    ".wwwww.",
    "wkkwkkw",
    "wkkwkkw",
    "wwwwwww",
    "wwwkwww",
    "wwkkkww",
    "wwwkwww",
    ".wwwww.",
    ".wwww..",
    "..www..",
    "..ww...",
    "...w...",
]


WALKER = [
    ["..###...", ".#####..", ".#E##E..", ".#####..", "..#m#...", "..ss....", ".sssaaaa",
     ".sssaaaa", ".sss....", ".sss....", ".ppp....", ".p.p....", "p...p...", "p...p..."],
    ["..###...", ".#####..", ".#E##E..", ".#####..", "..#m#...", "..ss....", ".sssaaaa",
     ".sssaaaa", ".sss....", ".sss....", ".ppp....", "..pp....", "..p.p...", ".p..p..."],
]
WALKER_COLS = [
    {"#": (90, 140, 70), "E": (255, 60, 40), "m": (40, 20, 20), "s": (60, 50, 80),
     "a": (90, 140, 70), "p": (50, 40, 35)},
    {"#": (110, 130, 90), "E": (230, 230, 120), "m": (40, 20, 20), "s": (90, 40, 40),
     "a": (110, 130, 90), "p": (35, 35, 55)},
    {"#": (80, 120, 90), "E": (255, 60, 40), "m": (40, 20, 20), "s": (50, 70, 60),
     "a": (80, 120, 90), "p": (45, 35, 30)},
]


def blend_px(c, x, y, col, a):
    x, y = int(round(x)), int(round(y))
    if 0 <= x < W and 0 <= y < H and a > 0:
        o = c.p[x, y]
        c.p[x, y] = tuple(int(o[i] + (col[i] - o[i]) * min(1, a)) for i in range(3))


def halloween_spooky(f, N):
    t = f / N
    flash = {58: 1.0, 59: 0.3, 60: 0.0, 61: 0.9, 62: 0.45, 63: 0.15}.get(f, 0.0)
    c = Canvas(lerp((6, 8, 22), (170, 175, 220), flash), lerp((2, 2, 6), (90, 90, 130), flash))
    for i in range(12):                                               # faint stars
        tw = 0.5 + 0.5 * math.sin(TAU * (t * (1 + i % 3) + rnd(i, 31)))
        c.px(rnd(i, 32) * W, rnd(i, 33) * 14, scale((150, 150, 190), 0.15 + 0.35 * tw))
    c.glow(46, 7, 13, (60, 70, 70), 0.6)                              # pale moon
    c.disc(46, 7, 5, (200, 210, 190))
    for dx, dy in ((-2, -1), (1, 2), (2, -2)):
        c.px(46 + dx, 7 + dy, (160, 170, 150))
    for k in range(2):                                                # clouds drift over it
        cx = (t + k * 0.5) % 1.0 * (W + 40) - 20
        for j in range(-9, 10):
            for r in range(3):
                a = 0.7 * (1 - abs(j) / 10) * (1 - r / 3)
                blend_px(c, cx + j, 5 + 3 * k + r, (14, 16, 30), a)
    if flash > 0.3:                                                   # face in the sky
        k = min(1.0, flash)
        shade = lerp((170, 175, 220), (25, 20, 45), 0.8 * k)
        for y in range(1, 17):                                        # face looming in the cloud
            for x in range(12, 41):
                d = ((x - 26) / 14) ** 2 + ((y - 9) / 9) ** 2
                if d <= 1.0:
                    blend_px(c, x, y, shade, 0.25 * k * (1 - d))
        for i in range(5):                                            # angry brows
            blend_px(c, 16 + i, 3 + i // 2, (10, 5, 15), 0.9 * k)
            blend_px(c, 36 - i, 3 + i // 2, (10, 5, 15), 0.9 * k)
        for ex in (20, 32):                                           # hollow eyes, staring
            for y in range(5, 10):
                for x in range(ex - 3, ex + 3):
                    if ((x - ex + 0.5) / 3) ** 2 + ((y - 7) / 2.5) ** 2 <= 1:
                        blend_px(c, x, y, (10, 5, 15), 0.9 * k)
            c.px(ex - 1, 7, (255, 30, 20))                             # red pupils
            c.px(ex, 7, (255, 30, 20))
        for y in (10, 11):                                            # nose
            blend_px(c, 26, y, (20, 15, 30), 0.8 * k)
        for x in range(19, 34):                                       # jagged grin
            y = 14 - (1 if x in (19, 33) else 0)
            blend_px(c, x, y, (10, 5, 15), 0.9 * k)
            if x % 2 == 0 and 19 < x < 33:
                blend_px(c, x, y - 1, (10, 5, 15), 0.9 * k)
            if x % 2 == 1 and 19 < x < 33:
                blend_px(c, x, y + 1, (10, 5, 15), 0.9 * k)
    if flash > 0.3:                                                   # the bolt
        x = 57
        for y in range(0, 12):
            x += (-1, 1, 0, 1, -1, 1)[y % 6]
            c.px(x, y, (255, 255, 255))
            c.px(x + 1, y, (200, 200, 255))
    c.sprite(DEAD_TREE, 0, 12, {"#": (4, 3, 6)})                   # dead tree
    c.rect(0, 26, W, 6, (10, 14, 10))                                 # ground
    for gx, gy, h in ((14, 20, 7), (25, 22, 5), (48, 21, 6), (58, 23, 4)):  # graves
        c.rect(gx, gy, 5, h, (48, 48, 58))
        c.rect(gx + 1, gy - 1, 3, 1, (48, 48, 58))
        c.rect(gx + 2, gy + 1, 1, 3, (30, 30, 38))
        c.rect(gx + 1, gy + 2, 3, 1, (30, 30, 38))
    for x in range(0, W, 3):                                          # iron fence
        c.rect(x, 24, 1, 4, (16, 16, 20))
        c.px(x, 23, (22, 22, 28))
    c.rect(0, 25, W, 1, (16, 16, 20))
    # zombies shambling across in front of the graves
    for i, (start, laps, ty) in enumerate(((0.0, 1, 13), (0.45, 1, 14), (0.7, 2, 12))):
        u = (start + laps * t) % 1.0
        x = u * (W + 24) - 12
        step = (f // 3 + i) % 2
        lurch = (f // 3 + i) % 2
        c.sprite(WALKER[step], int(x), ty + lurch, WALKER_COLS[i])
    # fog: two layers of slow sine noise along the ground
    for x in range(W):
        for layer, (base, amp, speed, alpha) in enumerate(((27, 2.5, 1, 0.45), (24, 2.0, -1, 0.25))):
            top = base + amp * math.sin(TAU * (x / 23 + speed * t)) + 1.2 * math.sin(TAU * (x / 9 - 2 * speed * t))
            for y in range(int(top), H):
                d = min(1, (y - top) / 3)
                blend_px(c, x, y, (70, 80, 95), alpha * d)
    if flash:                                                         # lightning
        c.im = Image.blend(c.im, Image.new("RGB", (W, H), (210, 215, 255)), 0.12 * flash)
    return c.im


# ---------------------------------------------------------------------
# Halloween peek (orange/black stripes, ghosts and zombies peek out from
# behind the black bars one at a time)
# ---------------------------------------------------------------------
PEEK_ORANGE = (230, 95, 15)
PEEK_BLACK = (14, 8, 6)
PEEK_BAR = 6                     # stripe width: orange 0-5, black 6-11, ...


def ghost_sprite(f, blink):
    """11x22 sheet ghost in the style of the reference: tall, plain, two oval eyes."""
    w, h = 11, 22
    im = {}
    for y in range(h):
        for x in range(w):
            if y < 6:                                   # rounded head
                if (x - 5) ** 2 + (y - 5.5) ** 2 * 1.1 > 30:
                    continue
            elif y >= h - 2:                            # wavy hem
                if y == h - 1 and (x + f // 3) % 3 == 0:
                    continue
            shade = (240, 232, 210) if x > 1 else (205, 198, 180)
            im[(x, y)] = shade
    for ex in (3, 6):
        rows = (7,) if blink else (6, 7, 8)
        for ey in rows:
            im[(ex, ey)] = (10, 6, 6)
            im[(ex + 1, ey)] = (10, 6, 6)
    return im, w, h


def zombie_sprite(f, blink):
    """14x20 zombie, facing right, arm reaching out in front."""
    w, h = 14, 20
    im = {}
    skin, dark = (120, 170, 80), (70, 110, 50)
    for y in range(0, 9):                               # head
        for x in range(0, 9):
            if (x, y) in ((0, 0), (8, 0)):
                continue
            im[(x, y)] = skin if x > 0 else dark
    for x in range(0, 9):                               # scruffy hair
        im[(x, 0)] = (40, 30, 20)
        if x % 3 != 1:
            im[(x, 1)] = (40, 30, 20)
    if blink:
        for x in (5, 6, 7):
            im[(x, 4)] = (20, 10, 10)
    else:
        for (x, y) in ((5, 3), (6, 3), (5, 4), (6, 4)):
            im[(x, y)] = (240, 240, 210)               # big eye
        im[(6, 4)] = (200, 20, 20)
        im[(2, 4)] = (240, 240, 210)                   # small eye
        im[(3, 4)] = (20, 10, 10)
    for x in range(3, 9):                               # stitched mouth
        im[(x, 7)] = (60, 20, 20)
    for x in (4, 6, 8):
        im[(x, 6)] = (60, 20, 20)
    for y in range(9, 11):                              # neck
        for x in (3, 4, 5):
            im[(x, y)] = dark
    for y in range(11, h):                              # torn shirt
        for x in range(0, 9):
            if y == h - 1 and x % 3 == 0:
                continue
            im[(x, y)] = (60, 80, 110) if (x + y) % 5 else (40, 55, 80)
    reach = round(math.sin(TAU * f / 10))               # arm reaching, wobbling
    for x in range(6, w):
        im[(x, 12 + (reach if x > 10 else 0))] = skin
        im[(x, 13 + (reach if x > 10 else 0))] = dark
    for (dx, dy) in ((13, 11), (13, 14)):               # fingers
        im[(dx, dy + reach)] = skin
    return im, w, h


def draw_peek(c, sprite, w, h, edge, shown, top, side):
    """Draw a sprite poking out of a black bar. side=-1: it emerges to the left
    of the bar's left edge; side=+1: to the right of the bar's right edge, and
    the sprite is mirrored to face the way it comes out."""
    for (x, y), col in sprite.items():
        if side > 0:
            sx = edge - w + shown + x                  # facing right
            if sx >= edge:
                c.px(sx, top + y, col)
        else:
            sx = edge - shown + (w - 1 - x)            # mirrored, facing left
            if sx < edge:
                c.px(sx, top + y, col)


PEEKS = [
    # (kind, bar edge x, side, peek px, top y)
    ("ghost", 42, -1, 9, 7),
    ("zombie", 24, 1, 11, 9),
    ("ghost", 54, -1, 8, 4),
    ("zombie", 30, -1, 12, 11),
]


def halloween_peek(f, N):
    c = Canvas()
    for x in range(W):
        col = PEEK_ORANGE if (x // PEEK_BAR) % 2 == 0 else PEEK_BLACK
        for y in range(H):
            c.p[x, y] = col
    slot = N // len(PEEKS)
    i, local = divmod(f, slot)
    kind, edge, side, peek, top = PEEKS[i]
    out_t, back_t = 9, slot - 8
    if local < out_t:
        shown = peek * ease_out_back(local / out_t)
    elif local < back_t:
        shown = peek
    else:
        shown = peek * (1 - (local - back_t) / (slot - back_t)) ** 2
    blink = local in (out_t + 8, out_t + 9)
    bob = round(math.sin(TAU * local / slot * 2)) if kind == "ghost" else 0
    sprite, w, h = (ghost_sprite if kind == "ghost" else zombie_sprite)(f, blink)
    draw_peek(c, sprite, w, h, edge, max(0, round(shown)), top + bob, side)
    return c.im


# ---------------------------------------------------------------------
# Halloween spiders (web in the corner, spiders scuttling across, one
# dangling on its thread)
# ---------------------------------------------------------------------
SPIDER = [
    ["#.......#", ".#.###.#.", "..####rr.", ".#.###.#.", "#.......#"],
    [".#.....#.", "#..###..#", ".#####rr.", "#..###..#", ".#.....#."],
]
BIG_SPIDER = [
    ["#....#.......#....", ".#...#.......#...#", "..#..#.#####.#..#.",
     "...##.#######.##..", "....##########rr#.", "....###########rr.",
     "...##.#######.##..", "..#..#.#####.#..#.", ".#...#.......#...#", "#....#.......#...."],
    ["..#....#.....#..#.", "..#....#.....#...#", "#..#..#.#####.#.#..",
     ".#.##.#######.##...", "....##########rr#.", "....###########rr.",
     ".#.##.#######.##...", "#..#..#.#####.#.#..", "..#....#.....#...#", "..#....#.....#..#."],
]


def halloween_spiders(f, N):
    t = f / N
    c = Canvas((80, 40, 100), (30, 10, 40))
    web = (150, 145, 165)
    for a in range(5):                                                # web in the corner
        ang = a / 4 * (math.pi / 2)
        for r in range(0, 20):
            c.px(r * math.cos(ang), r * math.sin(ang), web)
    for ring in (5, 10, 15):
        for a in range(4):
            a0, a1 = a / 4 * (math.pi / 2), (a + 1) / 4 * (math.pi / 2)
            x0, y0 = ring * math.cos(a0), ring * math.sin(a0)
            x1, y1 = ring * math.cos(a1), ring * math.sin(a1)
            for k in range(8):
                u = k / 7
                sag = 1.2 * math.sin(math.pi * u)
                c.px(x0 + (x1 - x0) * u - sag * 0.7, y0 + (y1 - y0) * u - sag * 0.7, web)
    body = {"#": (6, 4, 8), "r": (255, 30, 20)}
    # dangling spider: lowers on its thread and climbs back up
    dy = 3 + 14 * (0.5 - 0.5 * math.cos(TAU * t))
    for y in range(0, int(dy)):
        c.px(50, y, web)
    sp = SPIDER[(f // 4) % 2]
    rot = [[sp[r][col] for r in range(len(sp))] for col in range(len(sp[0]))]   # head down
    c.sprite(["".join(row) for row in rot], 48, int(dy), body)
    # small spiders scuttling both ways
    for i, (laps, y, rev) in enumerate(((2, 20, False), (3, 26, True), (2, 13, True), (3, 7, False), (4, 17, False), (2, 28, True))):
        u = (rnd(i, 41) + laps * t) % 1.0
        x = u * (W + 12) - 10
        frames = SPIDER[(f // 2 + i) % 2]
        if rev:
            x = W - x - 9
            frames = [r[::-1] for r in frames]
        c.sprite(frames, int(x), y + (f // 2 + i) % 2 * 0, body)
    # the big one, slow and heavy, along the bottom
    u = t % 1.0
    x = u * (W + 40) - 20
    c.sprite(BIG_SPIDER[(f // 3) % 2], int(x), 21, {"#": (12, 8, 14), "r": (255, 40, 20)})
    return c.im


# ---------------------------------------------------------------------
# Halloween eye (one big bloodshot eyeball looking around, blinking)
# ---------------------------------------------------------------------
EYE_GAZE = [  # (frame, dx, dy) keyframes; holds then darts
    (0, 0, 0), (12, 0, 0), (16, -11, -1), (34, -11, -1), (37, 10, 2), (52, 10, 2),
    (55, 4, -4), (66, 4, -4), (69, 0, 0), (100, 0, 0)]
EYE_BLINKS = (44, 84)


def _veins():
    rng = random.Random(13)
    veins = []
    for _ in range(14):
        ang = rng.random() * TAU
        x, y = 32 + 29 * math.cos(ang), 16 + 15 * math.sin(ang)
        path = []
        for _ in range(rng.randint(6, 11)):
            path.append((x, y))
            x += (32 - x) * 0.12 + rng.uniform(-1, 1)
            y += (16 - y) * 0.12 + rng.uniform(-1, 1)
        veins.append(path)
    return veins


VEINS = _veins()


def halloween_eye(f, N):
    c = Canvas((40, 0, 8), (12, 0, 2))
    for i in range(len(EYE_GAZE) - 1):                                # gaze
        f0, x0, y0 = EYE_GAZE[i]
        f1, x1, y1 = EYE_GAZE[i + 1]
        if f0 <= f < f1:
            u = (f - f0) / (f1 - f0)
            u = u * u * (3 - 2 * u)
            gx, gy = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
            break
    rx, ry = 29, 14
    for y in range(H):                                                # eyeball
        for x in range(W):
            d = ((x - 32) / rx) ** 2 + ((y - 16) / ry) ** 2
            if d <= 1:
                c.p[x, y] = lerp((245, 238, 225), (170, 120, 120), d ** 1.5)
    for path in VEINS:
        for k in range(len(path) - 1):
            (xa, ya), (xb, yb) = path[k], path[k + 1]
            for j in range(4):
                x, y = xa + (xb - xa) * j / 4, ya + (yb - ya) * j / 4
                if ((x - 32) / rx) ** 2 + ((y - 16) / ry) ** 2 <= 1:
                    blend_px(c, x, y, (190, 25, 35), 0.8 - k * 0.07)
    ix, iy = 32 + gx, 16 + gy
    dil = 1 + 0.25 * math.sin(TAU * f / N * 2)
    for y in range(H):                                                # iris and pupil
        for x in range(W):
            if ((x - 32) / rx) ** 2 + ((y - 16) / ry) ** 2 > 1:
                continue
            r = math.hypot(x - ix, y - iy)
            if r <= 3.2 * dil:
                c.p[x, y] = (4, 2, 4)
            elif r <= 8:
                streak = 0.75 + 0.25 * math.sin(math.atan2(y - iy, x - ix) * 9)
                col = lerp((150, 200, 40), (40, 90, 20), (r - 3) / 5)
                c.p[x, y] = scale(col, streak)
            elif r <= 9:
                c.p[x, y] = (20, 40, 10)
    c.px(ix + 2, iy - 2, (255, 255, 255))                             # wet highlight
    c.px(ix + 3, iy - 2, (200, 200, 200))
    close = 0.0                                                       # eyelids
    for b in EYE_BLINKS:
        if b <= f < b + 6:
            close = (1, 1, 1, 0.6, 0.25, 0)[f - b] if f > b else 0.6
    lid = (90, 30, 50)
    for x in range(W):
        half = ry * math.sqrt(max(0, 1 - ((x - 32) / rx) ** 2))
        top = 16 - half + (2 * half) * 0.5 * close + 1.5                # resting lid covers the top a little
        bot = 16 + half - (2 * half) * 0.5 * close
        for y in range(H):
            inside = ((x - 32) / (rx + 2)) ** 2 + ((y - 16) / (ry + 2)) ** 2 <= 1
            if inside and (y < top or y > bot):
                c.p[x, y] = lid if y < top else scale(lid, 0.8)
        c.px(x, top, (15, 0, 8)) if half else None
    return c.im


ANIMS = {
    # name: (frame function, frames, palette size)
    "thanksgiving": (thanksgiving, 48, 96),
    "halloween": (halloween, 60, 128),
    "christmas": (christmas, 60, 128),
    "oh_mary": (oh_mary, 36, 128),
    "news_intro": (news_intro, 22, 64),
    "claude": (claude, 60, 64),
    "halloween_party": (halloween_party, 80, 128),
    "halloween_spooky": (halloween_spooky, 100, 128),
    "halloween_peek": (halloween_peek, 120, 64),
    "halloween_spiders": (halloween_spiders, 120, 64),
    "halloween_eye": (halloween_eye, 100, 128),
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
