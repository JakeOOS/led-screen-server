# =====================================================================
#  SCREEN APP  (lives as device_app.py on the server, app.py on device)
# =====================================================================
#  Capabilities: trains, weather, scrolling messages, a .bin animation
#  pulled from GitHub, and a clock. WHICH of these show, and how bright,
#  is decided by the SERVER's schedule (so the phone app can edit it later).
#  This file just obeys: it renders whatever modes the server allows, at
#  whatever brightness the server sends.
#
#  No crash handler at the bottom on purpose -- the bootloader handles that.
# =====================================================================

import time
import network
import urequests
import interstate75
import machine
import gc
import os

DEVICE_SECRET = "tulsehill-screen-2026-x7k2m9"    # must match DEVICE_SECRET in Render

# --- CONFIG ---
WIFI_SSID = "SKYWI5D4"
WIFI_PASSWORD = "Jx14ShNK5u3YPH"
SERVER_URL = "https://led-screen-server.onrender.com"
DEVICE_ID = "tulsehill-01"
POLL_INTERVAL = 20           # seconds between server data polls
SCREEN_SECONDS = 12          # seconds each screen shows before the loop advances

# The special animation you store in GitHub as a raw .bin (64x32x3 per frame)
ANIM_URL = "https://raw.githubusercontent.com/JakeOOS/TidBytTulse/main/anim.bin"
FRAME_SIZE = 64 * 32 * 3
ANIM_REFRESH = 3600          # re-download the animation at most once an hour

# --- COLORS ---
COL_WHITE  = (255, 255, 255)
COL_RED    = (255, 50, 50)
COL_BLUE   = (50, 150, 255)
COL_GREY   = (80, 80, 80)
COL_ORANGE = (255, 140, 0)
COL_CYAN   = (0, 200, 255)
COL_BLACK  = (0, 0, 0)
COL_GREEN  = (0, 255, 0)

CURRENT_BRIGHTNESS = 0.6
BRIGHTNESS_LUT = bytearray([int(i * CURRENT_BRIGHTNESS) for i in range(256)])
current_anim_frame = -1

# Animation metadata cache (filled by load_anim_meta). Supports the new
# palette/indexed format (magic 'LDA1', ~2KB/frame) and the legacy raw-RGB
# format (6KB/frame), auto-detected from the file header.
ANIM = {"loaded": False, "indexed": False, "w": 64, "h": 32,
        "nframes": 0, "ncolors": 0, "offset": 0, "fbytes": FRAME_SIZE,
        "pal": None, "pens": None}

# --- HARDWARE INIT ---
try:
    i75 = interstate75.Interstate75(display=interstate75.DISPLAY_INTERSTATE75_64X32, panel_type=interstate75.PANEL_FM6126A)
except AttributeError:
    i75 = interstate75.Interstate75(display=interstate75.DISPLAY_INTERSTATE75_64X32)
graphics = i75.display

# =====================================================================
# --- FONTS ---
# =====================================================================
FONT_3X5 = {
    'A': [" # ", "# #", "###", "# #", "# #"], 'B': ["## ", "# #", "## ", "# #", "## "],
    'C': [" ##", "#  ", "#  ", "#  ", " ##"], 'D': ["## ", "# #", "# #", "# #", "## "],
    'E': ["###", "#  ", "## ", "#  ", "###"], 'F': ["###", "#  ", "## ", "#  ", "#  "],
    'G': [" ##", "#  ", "# #", "###", "  #"], 'H': ["# #", "# #", "###", "# #", "# #"],
    'I': ["###", " # ", " # ", " # ", "###"], 'J': ["###", "  #", "  #", "# #", " # "],
    'K': ["# #", "# #", "## ", "# #", "# #"], 'L': ["#  ", "#  ", "#  ", "#  ", "###"],
    'M': ["# #", "###", "###", "# #", "# #"], 'N': [" # ", "# #", "# #", "# #", "# #"],
    'O': [" # ", "# #", "# #", "# #", " # "], 'P': ["## ", "# #", "## ", "#  ", "#  "],
    'Q': [" # ", "# #", "# #", " ##", "  #"], 'R': ["## ", "# #", "## ", "# #", "# #"],
    'S': [" ##", "#  ", " # ", "  #", "## "], 'T': ["###", " # ", " # ", " # ", " # "],
    'U': ["# #", "# #", "# #", "# #", " # "], 'V': ["# #", "# #", "# #", " # ", " # "],
    'W': ["# #", "# #", "# #", "###", "# #"], 'X': ["# #", " # ", " # ", " # ", "# #"],
    'Y': ["# #", "# #", " # ", " # ", " # "], 'Z': ["###", "  #", " # ", "#  ", "###"],
    '0': ["###", "# #", "# #", "# #", "###"], '1': [" # ", "## ", " # ", " # ", "###"],
    '2': ["###", "  #", " # ", "#  ", "###"], '3': ["## ", "  #", " ##", "  #", "## "],
    '4': ["# #", "# #", "###", "  #", "  #"], '5': ["###", "#  ", "###", "  #", "###"],
    '6': ["###", "#  ", "###", "# #", "###"], '7': ["###", "  #", "  #", " # ", " # "],
    '8': ["###", "# #", "###", "# #", "###"], '9': ["###", "# #", "###", "  #", "  #"],
    ' ': ["   ", "   ", "   ", "   ", "   "], '-': ["   ", "   ", "###", "   ", "   "],
    '|': [" # ", " # ", " # ", " # ", " # "]
}

FONT_4X6 = {
    'A': [" ## ", "#  #", "#  #", "####", "#  #", "#  #"], 'B': ["### ", "#  #", "### ", "#  #", "#  #", "### "],
    'C': [" ###", "#   ", "#   ", "#   ", "#   ", " ###"], 'D': ["### ", "#  #", "#  #", "#  #", "#  #", "### "],
    'E': ["####", "#   ", "### ", "#   ", "#   ", "####"], 'F': ["####", "#   ", "### ", "#   ", "#   ", "#   "],
    'G': [" ###", "#   ", "#   ", "# ##", "#  #", " ###"], 'H': ["#  #", "#  #", "####", "#  #", "#  #", "#  #"],
    'I': ["###", " # ", " # ", " # ", " # ", "###"], 'J': ["  ##", "   #", "   #", "   #", "#  #", " ## "],
    'K': ["#  #", "# # ", "##  ", "# # ", "#  #", "#  #"], 'L': ["#   ", "#   ", "#   ", "#   ", "#   ", "####"],
    'M': ["#  #", "####", "####", "#  #", "#  #", "#  #"], 'N': ["#  #", "## #", "####", "# ##", "#  #", "#  #"],
    'O': [" ## ", "#  #", "#  #", "#  #", "#  #", " ## "], 'P': ["### ", "#  #", "#  #", "### ", "#   ", "#   "],
    'Q': [" ## ", "#  #", "#  #", "#  #", "# ##", " ###"], 'R': ["### ", "#  #", "#  #", "### ", "# # ", "#  #"],
    'S': [" ###", "#   ", " ## ", "   #", "   #", "### "], 'T': ["###", " # ", " # ", " # ", " # ", " # "],
    'U': ["#  #", "#  #", "#  #", "#  #", "#  #", " ## "], 'V': ["#  #", "#  #", "#  #", "#  #", " ## ", " ## "],
    'W': ["#  #", "#  #", "#  #", "####", "####", "#  #"], 'X': ["#  #", "#  #", " ## ", " ## ", "#  #", "#  #"],
    'Y': ["# #", "# #", " # ", " # ", " # ", " # "], 'Z': ["####", "   #", "  # ", " #  ", "#   ", "####"],
    '0': [" ## ", "#  #", "# ##", "## #", "#  #", " ## "], '1': [" # ", "## ", " # ", " # ", " # ", "###"],
    '2': [" ## ", "#  #", "   #", "  # ", " #  ", "####"], '3': ["### ", "   #", " ## ", "   #", "   #", "### "],
    '4': ["#  #", "#  #", "####", "   #", "   #", "   #"], '5': ["####", "#   ", "### ", "   #", "   #", "### "],
    '6': [" ## ", "#   ", "### ", "#  #", "#  #", " ## "], '7': ["####", "   #", "  # ", "  # ", " #  ", " #  "],
    '8': [" ## ", "#  #", " ## ", "#  #", "#  #", " ## "], '9': [" ## ", "#  #", "#  #", " ###", "   #", " ## "],
    ' ': ["   ", "   ", "   ", "   ", "   ", "   "], '-': ["    ", "    ", "####", "    ", "    ", "    "],
    ':': [" ", "#", " ", "#", " ", " "], '.': [" ", " ", " ", " ", " ", "#"],
    '!': ["#", "#", "#", "#", " ", "#"], '?': [" ## ", "#  #", "  # ", " #  ", "    ", " #  "],
    '|': [" # ", " # ", " # ", " # ", " # ", " # "]
}

FONT_BOLD_5X5 = {
    'A': [" ### ", "## ##", "#####", "## ##", "## ##"], 'B': ["#### ", "## ##", "#### ", "## ##", "#### "],
    'C': [" ####", "##   ", "##   ", "##   ", " ####"], 'D': ["#### ", "## ##", "## ##", "## ##", "#### "],
    'E': ["#####", "##   ", "###  ", "##   ", "#####"], 'F': ["#####", "##   ", "###  ", "##   ", "##   "],
    'G': [" ####", "##   ", "## ##", "## ##", " ####"], 'H': ["## ##", "## ##", "#####", "## ##", "## ##"],
    'I': ["###", " # ", " # ", " # ", "###"], 'J': ["  ###", "   ##", "   ##", "## ##", " ### "],
    'K': ["## ##", "## ##", "###  ", "## ##", "## ##"], 'L': ["##   ", "##   ", "##   ", "##   ", "#####"],
    'M': ["## ##", "#####", "#####", "## ##", "## ##"], 'N': ["## ##", "#### ", "#####", "## ##", "## ##"],
    'O': [" ### ", "## ##", "## ##", "## ##", " ### "], 'P': ["#### ", "## ##", "#### ", "##   ", "##   "],
    'Q': [" ### ", "## ##", "## ##", "## ##", " ####"], 'R': ["#### ", "## ##", "#### ", "## ##", "## ##"],
    'S': [" ####", "##   ", " ### ", "   ##", "#### "], 'T': ["#####", "  ##  ", "  ##  ", "  ##  ", "  ##  "],
    'U': ["## ##", "## ##", "## ##", "## ##", " ### "], 'V': ["## ##", "## ##", "## ##", " ### ", "  #  "],
    'W': ["## ##", "#####", "#####", "#####", "## ##"], 'X': ["## ##", "## ##", " ### ", "## ##", "## ##"],
    'Y': ["## ##", "## ##", " ### ", "  ## ", "  ## "], 'Z': ["#####", "   ##", "  ## ", " ##  ", "#####"],
    '0': [" ### ", "## ##", "## ##", "## ##", " ### "], '1': ["  ## ", " ### ", "  ## ", "  ## ", "#####"],
    '2': ["#### ", "     ##", " ### ", "##   ", "#####"], '3': ["#### ", "     ##", " ### ", "     ##", "#### "],
    '4': ["## ##", "## ##", "#####", "   ##", "   ##"], '5': ["#####", "##   ", "#### ", "     ##", "#### "],
    '6': [" ### ", "##   ", "#### ", "## ##", " ### "], '7': ["#####", "   ##", "  ## ", " ##  ", " ##  "],
    '8': [" ### ", "## ##", " ### ", "## ##", " ### "], '9': [" ### ", "## ##", " ####", "   ##", " ### "],
    ' ': ["     ", "     ", "     ", "     ", "     "], '-': ["     ", "     ", "#####", "     ", "     "],
    '?': [" ### ", "   ##", "  ## ", "     ", "  ## "], '!': ["  ## ", "  ## ", "  ## ", "     ", "  ## "]
}

FONT_TALL_5X11 = {
    '0': [" ### ", "## ##", "## ##", "## ##", "## ##", "## ##", "## ##", "## ##", "## ##", "## ##", " ### "],
    '1': ["  ## ", " ### ", "  ## ", "  ## ", "  ## ", "  ## ", "  ## ", "  ## ", "  ## ", "  ## ", "#####"],
    '2': [" ### ", "## ##", "   ##", "   ##", "  ## ", " ##  ", "##   ", "##   ", "##   ", "##   ", "#####"],
    '3': ["#####", "   ##", "   ##", "   ##", "  ###", "   ##", "   ##", "   ##", "   ##", "   ##", "#####"],
    '4': ["   ##", "  ###", " ## #", "## ##", "## ##", "#####", "   ##", "   ##", "   ##", "   ##", "   ##"],
    '5': ["#####", "##   ", "##   ", "#### ", "   ##", "   ##", "   ##", "   ##", "## ##", "## ##", " ### "],
    '6': [" ### ", "##   ", "##   ", "##   ", "#### ", "## ##", "## ##", "## ##", "## ##", "## ##", " ### "],
    '7': ["#####", "   ##", "   ##", "   ##", "  ## ", "  ## ", "  ## ", " ##  ", " ##  ", " ##  ", " ##  "],
    '8': [" ### ", "## ##", "## ##", "## ##", " ### ", "## ##", "## ##", "## ##", "## ##", "## ##", " ### "],
    '9': [" ### ", "## ##", "## ##", "## ##", "## ##", " ####", "   ##", "   ##", "   ##", "## ##", " ### "],
    ':': ["   ", "   ", "   ", " ##", " ##", "   ", " ##", " ##", "   ", "   ", "   "]
}

# =====================================================================
# --- WEATHER ICONS ---
# =====================================================================
ICON_PALETTE = {
    ' ': (0, 0, 0), 'Y': (255, 240, 0), 'W': (255, 255, 255), 'G': (140, 140, 140), 'C': (0, 200, 255)
}

# 13x11 pixel icons traced from the reference image.
ICON_SUN = [
    "    Y   Y    ","  Y  YYY  Y  ","    YYYYY    ",
    " Y YYYYYYY Y ","   YYYYYYY   ","   YYYYYYY   ",
    " Y YYYYYYY Y ","    YYYYY    ","  Y  YYY  Y  ",
    "    Y   Y    ","             ",
]
ICON_PARTLY = [
    "       YYY   ","     YYYYYYY ","    YYYYYY   ",
    "  WWYYYYYYY  "," WWWWWYYYYY  "," WWWWWWWWWW  ",
    "WWWWWWWWWWWW ","WWWWWWWWWWWW "," WWWWWWWWWW  ",
    "             ","             ",
]
ICON_CLOUDY = [
    "             ","   WWWW      ","  WWWWWWW    ",
    " WWWWWWWWWW  ","WWWWWWWWWWWW ","WWWWWWWWWWWW ",
    "WWWWWWWWWWWW "," WWWWWWWWWW  ","  GGGGGGGG   ",
    "             ","             ",
]
ICON_RAIN = [
    "   WWWW      ","  WWWWWWW    "," WWWWWWWWWW  ",
    "WWWWWWWWWWWW ","WWWWWWWWWWWW "," WWWWWWWWWW  ",
    " C  C  C  C  ","  C  C  C    "," C  C  C  C  ",
    "  C  C  C    ","             ",
]
ICON_THUNDER = [
    "   WWWW      ","  WWWWWWW    "," WWWWWWWWWW  ",
    "WWWWWWWWWWWW ","WWWWWWWWWWWW "," WWWWWWWWWW  ",
    "    YYYY     ","   YYYYYY    ","    YYYY     ",
    "C     YY   C ","      Y      ",
]
ICON_SNOW = [
    "   WWWW      ","  WWWWWWW    "," WWWWWWWWWW  ",
    "WWWWWWWWWWWW ","WWWWWWWWWWWW "," WWWWWWWWWW  ",
    " W G W G W   ","WGWGWGWGWGW  "," W G W G W   ",
    "   G   G     ","             ",
]

# Map OWM condition strings to icons.
WEATHER_ICONS = {
    'clear':       ICON_SUN,
    'clouds':      ICON_CLOUDY,
    'partly':      ICON_PARTLY,
    'rain':        ICON_RAIN,
    'drizzle':     ICON_RAIN,
    'thunderstorm':ICON_THUNDER,
    'snow':        ICON_SNOW,
}

# =====================================================================
# --- GRAPHICS ENGINE ---
# =====================================================================
class Display:
    def __init__(self):
        self.width = 64
        self.height = 32
        self.pens = {}

    def reset_pens(self):
        self.pens = {}

    def create_pen(self, color):
        if color not in self.pens:
            r = int(color[0] * CURRENT_BRIGHTNESS)
            g = int(color[1] * CURRENT_BRIGHTNESS)
            b = int(color[2] * CURRENT_BRIGHTNESS)
            self.pens[color] = graphics.create_pen(r, g, b)
        return self.pens[color]

    def clear(self):
        graphics.set_pen(self.create_pen(COL_BLACK))
        graphics.clear()

    def pixel(self, x, y, color):
        if 0 <= x < 64 and 0 <= y < 32:
            graphics.set_pen(self.create_pen(color))
            graphics.pixel(x, y)

    def text(self, text_str, x, y, color, font=FONT_3X5, scale=1, spacing=1):
        cursor_x = x
        for char in str(text_str).upper():
            if char in font:
                grid = font[char]
                char_w = len(grid[0])
                for r, row in enumerate(grid):
                    for c, pix in enumerate(row):
                        if pix != " " and pix != "\xa0":
                            if scale == 1:
                                self.pixel(cursor_x + c, y + r, color)
                            else:
                                graphics.set_pen(self.create_pen(color))
                                graphics.rectangle(cursor_x + (c * scale), y + (r * scale), scale, scale)
                cursor_x += (char_w * scale) + spacing
            else:
                cursor_x += (3 * scale) + spacing

    def draw_pixel_icon(self, icon_array, x, y):
        for row_idx, row in enumerate(icon_array):
            for col_idx, char in enumerate(row):
                if char != ' ':
                    color = ICON_PALETTE.get(char, COL_WHITE)
                    self.pixel(x + col_idx, y + row_idx, color)

screen = Display()

# =====================================================================
# --- WIFI ---
# =====================================================================
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    time.sleep(0.5)
    try: wlan.active(True)
    except OSError: return False
    time.sleep(1)
    if not wlan.isconnected():
        try: wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        except OSError: return False
        max_wait = 10
        while max_wait > 0:
            if wlan.isconnected(): break
            time.sleep(1)
            max_wait -= 1
    return wlan.isconnected()

def check_wifi():
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected(): return connect_wifi()
    return True

# =====================================================================
# --- ASK THE SERVER WHAT TO SHOW ---
# =====================================================================
def fetch_display_state(current_state):
    try:
        gc.collect()
        url = SERVER_URL + "/api/device/" + DEVICE_ID + "/display"
        headers = {}
        if DEVICE_SECRET:
            headers["x-device-secret"] = DEVICE_SECRET
        # Keep this short: the poll runs inside the render loop, so the
        # screen is frozen for however long this request takes.
        r = urequests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            r.close()
            trains = []
            for row in data.get("trains", []):
                times = [{"text": t["text"], "color": tuple(t["color"])} for t in row.get("times", [])]
                trains.append({"badge": row["badge"], "badge_col": tuple(row["badge_col"]), "times": times})
            return {
                "brightness": data.get("brightness", 0.6),
                "allowed_modes": data.get("allowed_modes", ["TRAINS", "WEATHER"]),
                "trains": trains,
                "weather": data.get("weather", []),
                "message": data.get("message", ""),
                "reboot": data.get("reboot", False),
                "epoch": data.get("epoch", 0),
                "tz_offset": data.get("tz_offset", 0),
                "anim_version": data.get("anim_version", 0),
                "paired": data.get("paired", True),
                "pair_code": data.get("pair_code", ""),
            }
        else:
            print("Server status", r.status_code)
            r.close()
    except Exception as e:
        print("Server poll failed:", e)
    return current_state

# =====================================================================
# --- ANIMATION (.bin from GitHub) ---
# =====================================================================
def anim_available():
    try:
        with open("anim.bin", "rb") as f:
            head = f.read(10)
        if len(head) >= 10 and head[0:4] == b"LDA1":
            return (head[8] | (head[9] << 8)) > 0     # nframes > 0
        return os.stat("anim.bin")[6] >= FRAME_SIZE
    except OSError:
        return False

def free_bytes():
    try:
        s = os.statvfs("/")
        return s[0] * s[3]
    except Exception:
        return -1

def _validate_anim(path, written):
    """Accept either the LDA1 palette format (size matches its own header) or
    the legacy raw-RGB format (a clean multiple of FRAME_SIZE)."""
    try:
        with open(path, "rb") as f:
            head = f.read(10)
        if len(head) >= 10 and head[0:4] == b"LDA1":
            w = head[4]; h = head[5]
            ncolors = head[6] | (head[7] << 8)
            nframes = head[8] | (head[9] << 8)
            expect = 10 + ncolors * 3 + nframes * w * h
            return nframes > 0 and written == expect
        return written > 0 and (written % FRAME_SIZE == 0)
    except OSError:
        return False

def load_anim_meta():
    """Read anim.bin's header (and palette, if indexed) into ANIM."""
    ANIM["loaded"] = False
    ANIM["pens"] = None
    try:
        with open("anim.bin", "rb") as f:
            head = f.read(10)
            if len(head) >= 10 and head[0:4] == b"LDA1":
                w = head[4]; h = head[5]
                ncolors = head[6] | (head[7] << 8)
                nframes = head[8] | (head[9] << 8)
                pal = f.read(ncolors * 3)
                ANIM.update(indexed=True, w=w, h=h, ncolors=ncolors,
                            nframes=nframes, offset=10 + ncolors * 3,
                            fbytes=w * h, pal=pal, loaded=True)
            else:
                f.seek(0, 2)
                size = f.tell()
                ANIM.update(indexed=False, w=64, h=32, ncolors=0,
                            nframes=size // FRAME_SIZE, offset=0,
                            fbytes=FRAME_SIZE, pal=None, loaded=True)
    except OSError:
        ANIM["loaded"] = False
    return ANIM["loaded"]

def build_anim_pens():
    """Precompute one pen per palette colour at the current brightness."""
    if not (ANIM["loaded"] and ANIM["indexed"] and ANIM["pal"]):
        ANIM["pens"] = None
        return
    lut = BRIGHTNESS_LUT
    pal = ANIM["pal"]
    cp = graphics.create_pen
    pens = []
    for i in range(ANIM["ncolors"]):
        pens.append(cp(lut[pal[i * 3]], lut[pal[i * 3 + 1]], lut[pal[i * 3 + 2]]))
    ANIM["pens"] = pens

def fetch_animation(url=None, secret=False):
    """Download the .bin, being careful with limited flash. Returns a short
    status string: 'OK', 'HTTP nnn', 'FULL nn' (disk), 'BAD SIZE', or 'ERR n'.
    url defaults to the standard ANIM_URL; secret=True sends the device
    secret header (needed for the server's preview endpoint)."""
    print("Fetching animation... free:", free_bytes())
    gc.collect()
    # Clear any half-written temp from a previous failed attempt.
    try: os.remove("anim.tmp")
    except OSError: pass
    try:
        headers = {"x-device-secret": DEVICE_SECRET} if secret else {}
        r = urequests.get((url or ANIM_URL) + "?t=" + str(time.ticks_ms()),
                          headers=headers, timeout=20)
        if r.status_code != 200:
            code = r.status_code
            r.close()
            return "HTTP %d" % code
        expected = None
        try:
            cl = r.headers.get("Content-Length")
            if cl: expected = int(cl)
        except Exception:
            expected = None

        # If the incoming file won't fit alongside the current one, drop the
        # old anim.bin first to make room (this is what beats error 28).
        if expected:
            fb = free_bytes()
            if 0 <= fb < expected + 20000:        # 20KB safety margin
                try: os.remove("anim.bin")
                except OSError: pass
                gc.collect()
            fb = free_bytes()
            if 0 <= fb < expected + 20000:        # still won't fit
                r.close()
                return "FULL %d" % (expected // 1024)

        written = 0
        try:
            with open("anim.tmp", "wb") as f:
                while True:
                    chunk = r.raw.read(512)
                    if not chunk: break
                    f.write(chunk)
                    written += len(chunk)
        finally:
            r.close()

        size_ok = (expected is None) or (written == expected)
        if size_ok and _validate_anim("anim.tmp", written):
            try: os.remove("anim.bin")
            except OSError: pass
            os.rename("anim.tmp", "anim.bin")
            ANIM["loaded"] = False        # force header/palette reload
            print("Animation updated:", written, "bytes")
            return "OK"
        print("Bad anim download:", written, "bytes")
        try: os.remove("anim.tmp")
        except OSError: pass
        return "BAD SIZE"
    except OSError as e:
        try: os.remove("anim.tmp")
        except OSError: pass
        return "ERR %s" % (e.args[0] if e.args else "?")
    except Exception as e:
        try: os.remove("anim.tmp")
        except OSError: pass
        print("Anim fetch error:", e)
        return "ERR"

def draw_status(lines, color=COL_CYAN):
    """A simple centred status/loading screen for boot and diagnostics."""
    screen.clear()
    total_h = len(lines) * 6 - 1
    y = (32 - total_h) // 2
    for ln in lines:
        w = len(ln) * 4 - 1
        x = max(0, (64 - w) // 2)
        screen.text(ln, x, y, color, font=FONT_3X5)
        y += 6
    i75.update()

def draw_checklist(steps):
    """Boot checklist. steps = list of [label, state] where state is one of
    'pending' (grey), 'active' (cyan), 'done' (green), 'fail' (red)."""
    screen.clear()
    y = 5
    for label, st in steps:
        if st == "done":
            dot = COL_GREEN; txt = COL_WHITE
        elif st == "active":
            dot = COL_CYAN; txt = COL_WHITE
        elif st == "fail":
            dot = COL_RED; txt = COL_RED
        else:
            dot = COL_GREY; txt = COL_GREY
        graphics.set_pen(screen.create_pen(dot))
        graphics.rectangle(2, y + 1, 3, 3)
        screen.text(label, 9, y, txt, font=FONT_3X5)
        y += 9
    i75.update()

def draw_pair_screen(code):
    screen.clear()
    screen.text("PAIR CODE", 14, 2, COL_CYAN, font=FONT_3X5)
    cw = len(code) * 6 - 1                         # FONT_BOLD_5X5 is 5 wide + 1 gap
    x = max(0, (64 - cw) // 2)
    screen.text(code, x, 11, COL_WHITE, font=FONT_BOLD_5X5)
    screen.text("ENTER IN APP", 8, 25, COL_GREY, font=FONT_3X5)

def draw_voxel_loader(lit, failed_indices=None):
    """Draw VOXEL centred on screen.
    V = internal boot   O = server   X = firmware OK   E = APIs   L = ready
    lit          = how many letters are solidly lit (0-5)
    failed_indices = set/list of letter indices that failed (shown red)"""
    WORD = "VOXEL"
    COLOURS = [
        (255,  80,  80),   # V - coral
        (255, 180,   0),   # O - amber
        ( 80, 255,  80),   # X - green
        (  0, 200, 255),   # E - cyan
        (180,  80, 255),   # L - purple
    ]
    GREY = (55, 55, 55)
    RED  = (200, 50, 50)
    FONT5 = {
        'V': ["## ##", "## ##", "## ##", " ### ", "  #  "],
        'O': [" ### ", "## ##", "## ##", "## ##", " ### "],
        'X': ["## ##", " ### ", " ### ", " ### ", "## ##"],
        'E': ["#####", "##   ", "###  ", "##   ", "#####"],
        'L': ["##   ", "##   ", "##   ", "##   ", "#####"],
    }
    if failed_indices is None:
        failed_indices = set()
    total_w = sum(len(FONT5[c][0]) + 1 for c in WORD) - 1
    x = (64 - total_w) // 2
    y = (32 - 5) // 2
    screen.clear()
    for i, ch in enumerate(WORD):
        if i in failed_indices:
            col = RED
        elif i < lit:
            col = COLOURS[i]
        else:
            col = GREY
        g = FONT5[ch]
        cw = len(g[0])
        for ry, row in enumerate(g):
            for rx, p in enumerate(row):
                if p == '#':
                    screen.pixel(x + rx, y + ry, col)
        x += cw + 1
    i75.update()


def draw_error_screen(errors):
    """Dark red background with error names. Shown for 3s after VOXEL if
    any stage failed. errors = list of short strings e.g. ['SERVER FAIL']."""
    screen.clear()
    graphics.set_pen(screen.create_pen((100, 0, 0)))
    graphics.clear()
    y = 2
    for line in errors:
        screen.text(line, 2, y, (255, 80, 80), font=FONT_3X5)
        y += 7
    i75.update()

def draw_animation(ref_ticks):
    global current_anim_frame
    if not ANIM["loaded"]:
        if not load_anim_meta():
            screen.clear()
            screen.text("NO ANIM", 16, 14, COL_RED, font=FONT_3X5)
            return
    nframes = ANIM["nframes"]
    if nframes <= 0:
        screen.clear()
        return
    frame_idx = (ref_ticks // 100) % nframes
    if frame_idx == current_anim_frame:
        return
    current_anim_frame = frame_idx
    fbytes = ANIM["fbytes"]
    try:
        with open("anim.bin", "rb") as f:
            f.seek(ANIM["offset"] + frame_idx * fbytes)
            data = f.read(fbytes)
    except OSError:
        ANIM["loaded"] = False
        return
    set_pen = graphics.set_pen
    pixel = graphics.pixel
    w = ANIM["w"]; h = ANIM["h"]
    if ANIM["indexed"]:
        if ANIM["pens"] is None:
            build_anim_pens()
        pens = ANIM["pens"]
        idx = 0
        for y in range(h):
            for x in range(w):
                set_pen(pens[data[idx]])
                pixel(x, y)
                idx += 1
    else:
        create_pen = graphics.create_pen
        lut = BRIGHTNESS_LUT
        idx = 0
        for y in range(h):
            for x in range(w):
                set_pen(create_pen(lut[data[idx]], lut[data[idx + 1]], lut[data[idx + 2]]))
                pixel(x, y)
                idx += 3

# =====================================================================
# --- RENDERERS ---
# =====================================================================
def draw_train_dashboard(dashboard_data, ref_time):
    screen.clear()
    if not dashboard_data:
        screen.text("CONNECTING...", 5, 12, COL_WHITE, font=FONT_3X5)
        return
    y_offsets = [0, 11, 22]
    for i in range(3):
        train_row = dashboard_data[i]
        y = y_offsets[i]
        times_list = train_row['times']
        if not times_list:
            screen.text("NO TRAINS", 19, y + 2, COL_GREY, font=FONT_3X5)
            continue
        comma_width, sep_width = 8, 12
        total_width = sum((len(item['text']) * 4) for item in times_list) + (len(times_list) - 1) * comma_width + sep_width
        scroll_speed = 210
        base_offset = -(int(ref_time / scroll_speed) % total_width) + 18
        loops_needed = (64 // total_width) + 2
        for loop_index in range(loops_needed):
            current_x = base_offset + (loop_index * total_width)
            if current_x > 64: continue
            for j, item in enumerate(times_list):
                txt = item['text']
                screen.text(txt, current_x, y + 2, item['color'], font=FONT_3X5)
                current_x += (len(txt) * 4)
                if j < len(times_list) - 1:
                    screen.text(", ", current_x, y + 2, COL_GREY, font=FONT_3X5)
                    current_x += comma_width
                else:
                    screen.text(" | ", current_x, y + 2, train_row['badge_col'], font=FONT_3X5)
                    current_x += sep_width
    for i in range(3):
        train_row = dashboard_data[i]
        y = y_offsets[i]
        graphics.set_pen(screen.create_pen(train_row['badge_col']))
        graphics.rectangle(0, y, 17, 10)
        screen.text(train_row['badge'], 2, y + 3, COL_BLACK, font=FONT_3X5)
        if i < 2:
            graphics.set_pen(screen.create_pen(COL_GREY))
            graphics.line(0, y + 10, 64, y + 10)

def draw_weather_3col(data, ref_ticks):
    screen.clear()
    if not data:
        screen.text("WEATHER...", 5, 12, COL_WHITE, font=FONT_3X5)
        return
    graphics.set_pen(screen.create_pen(COL_GREY))
    graphics.line(21, 0, 21, 32)
    graphics.line(43, 0, 43, 32)
    col_starts = [1, 22, 44]
    col_w = 20          # usable width per column (leaving 1px for divider)
    for i, day in enumerate(data):
        if i > 2: break
        x_base = col_starts[i]
        icon = WEATHER_ICONS.get(day['icon_name'], ICON_CLOUDY)
        icon_w = len(icon[0])
        icon_x = x_base + (col_w - icon_w) // 2
        for ry, row in enumerate(icon):
            for rx, ch in enumerate(row):
                if ch != ' ' and rx < col_w:   # clip to column width
                    c = ICON_PALETTE.get(ch, COL_WHITE)
                    screen.pixel(icon_x + rx, 1 + ry, c)
        # Day label centred in column
        lbl = day['day']
        lw = len(lbl) * 4 - 1
        lx = x_base + (col_w - lw) // 2
        screen.text(lbl, lx, 13, COL_CYAN, font=FONT_3X5)
        # Temps: low (blue) / high (red)
        lo = str(day['low']); hi = str(day['high'])
        total_w = (len(lo) * 4 - 1) + 2 + (len(hi) * 4 - 1)
        tx = x_base + (col_w - total_w) // 2
        screen.text(lo, tx, 22, COL_BLUE, font=FONT_3X5)
        screen.text(hi, tx + (len(lo) * 4 - 1) + 2, 22, COL_RED, font=FONT_3X5)

def get_word_width(word, scale=1):
    w = 0
    for c in word:
        w += len(FONT_BOLD_5X5.get(c, ["     "])[0]) * scale + 1
    return w

def wrap_text_to_lines(text, max_w=62, scale=1):
    words = text.split(" ")
    lines = []
    current_line = ""
    for word in words:
        if not word: continue
        current_w = get_word_width(current_line + " " + word, scale) if current_line else get_word_width(word, scale)
        if not current_line:
            current_line = word
        elif current_w <= max_w:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

# Display scale used for the "beautiful" oversized message rendering, and the
# ceiling on how many lines it may take up before we fall back to the normal
# size (past this, the big font starts looking cramped rather than striking).
DISPLAY_SCALE = 2
DISPLAY_MAX_LINES = 3

def draw_phone_screen(msg, ref_time):
    screen.clear()
    if not msg:
        return

    # Prefer a big "display" rendering of the bold font -- only fall back to
    # the normal size (with scrolling if needed) if the message is too long
    # to sit statically on screen at the larger scale.
    big_lines = wrap_text_to_lines(msg, max_w=62, scale=DISPLAY_SCALE)
    line_h_big = 6 * DISPLAY_SCALE + 1
    total_height_big = len(big_lines) * line_h_big - 1
    if len(big_lines) <= DISPLAY_MAX_LINES and total_height_big <= 32:
        y_start = (32 - total_height_big) // 2
        for line in big_lines:
            line_w = get_word_width(line, DISPLAY_SCALE) - 1
            x = (64 - line_w) // 2
            screen.text(line, x, y_start, COL_WHITE, font=FONT_BOLD_5X5, scale=DISPLAY_SCALE, spacing=1)
            y_start += line_h_big
        return

    lines = wrap_text_to_lines(msg, max_w=62)
    total_height = len(lines) * 7 - 1
    if total_height <= 32:
        y_start = (32 - total_height) // 2
        for line in lines:
            line_w = get_word_width(line) - 1
            x = (64 - line_w) // 2
            screen.text(line, x, y_start, COL_WHITE, font=FONT_BOLD_5X5, spacing=1)
            y_start += 7
    else:
        ms_per_pixel = 150
        distance = total_height - 32
        scroll_time = distance * ms_per_pixel
        cycle_time = scroll_time + 2000
        current_cycle_time = ref_time % cycle_time
        if current_cycle_time < scroll_time:
            offset_y = 0 - (current_cycle_time // ms_per_pixel)
        else:
            offset_y = 0 - distance
        for line in lines:
            if -7 <= offset_y < 32:
                line_w = get_word_width(line) - 1
                x = (64 - line_w) // 2
                screen.text(line, x, offset_y, COL_WHITE, font=FONT_BOLD_5X5, spacing=1)
            offset_y += 7

def draw_clock(local_struct):
    screen.clear()
    hh = "%02d" % local_struct[3]
    mm = "%02d" % local_struct[4]
    screen.text(hh + ":" + mm, 5, 5, COL_WHITE, font=FONT_TALL_5X11, scale=2, spacing=2)

# =====================================================================
# --- CORE LOOP ---
# =====================================================================
def main():
    print("Boot free bytes:", free_bytes())
    state = {"brightness": 0.2, "allowed_modes": ["TRAINS", "WEATHER"],
             "trains": [], "weather": [], "message": "", "reboot": False,
             "epoch": 0, "tz_offset": 0, "paired": True, "pair_code": ""}

    # --- VOXEL boot loader -------------------------------------------
    # V = internal boot   O = server   X = firmware OK   E = APIs   L = ready
    # Each letter takes at least 1 second. Failed letters go red, then
    # an error screen lists what went wrong for 3 seconds before proceeding.
    LETTER_MIN = 1.0
    lit = 0
    failed_set = set()
    errors = []

    def light(ok, error_label=None):
        nonlocal lit
        if not ok:
            failed_set.add(lit)
            if error_label:
                errors.append(error_label)
        lit += 1
        draw_voxel_loader(lit, failed_set)

    def wait_min(start_t):
        rem = LETTER_MIN - (time.time() - start_t)
        if rem > 0:
            time.sleep(rem)

    # V — internal boot (always succeeds if we got here)
    draw_voxel_loader(0)
    t = time.time()
    wait_min(t)
    light(True)

    # O — server connection (retry a few times: WiFi may still be settling
    # right after boot, and the server can be slow on the first request)
    t = time.time()
    have_server = False
    for attempt in range(3):
        if check_wifi():
            state = fetch_display_state(state)
            have_server = bool(state.get("epoch"))
        if have_server:
            break
        time.sleep(2)
    wait_min(t)
    light(have_server, "SERVER FAIL" if not have_server else None)

    # X — firmware (always green: if we're running, code loaded fine)
    t = time.time()
    wait_min(t)
    light(True)

    # E — APIs. Only expect data for modes the server actually scheduled:
    # with catalogue-based schedules, trains/weather are legitimately empty
    # when the active time slot doesn't include those screens.
    t = time.time()
    modes = state.get("allowed_modes", [])
    weather_ok = bool(state.get("weather")) or "WEATHER" not in modes
    trains_ok  = bool(state.get("trains"))  or "TRAINS" not in modes
    api_ok = have_server and weather_ok and trains_ok
    if have_server:
        if not weather_ok: errors.append("WEATHER FAIL")
        if not trains_ok:  errors.append("TRAINS FAIL")
    wait_min(t)
    light(api_ok, None)    # error labels already appended above

    # L — ready
    t = time.time()
    wait_min(t)
    light(True)

    # If anything failed, show the error screen for 3 seconds then continue.
    if errors:
        draw_error_screen(errors)
        time.sleep(3)

    # Brief hold on the complete VOXEL before main display
    if not errors:
        time.sleep(0.4)

    sync_tick = time.ticks_ms()
    # If the boot poll succeeded, wait the normal interval before re-polling.
    # If it failed, poll again straight away so live data appears quickly.
    last_poll = time.time() if have_server else time.time() - POLL_INTERVAL
    last_anim_fetch = -9999
    last_anim_version = 0
    last_brightness = -1
    last_message = ""
    last_mode = ""
    priority_until = 0
    global CURRENT_BRIGHTNESS, BRIGHTNESS_LUT, current_anim_frame

    last_slot = -1

    while True:
        now = time.time()
        now_ticks = time.ticks_ms()

        # Poll on a screen-change boundary so any network stall lands
        # between screens instead of freezing mid-animation. If we're badly
        # overdue (single-screen cycle), poll anyway.
        slot = int(now // SCREEN_SECONDS)
        at_boundary = slot != last_slot
        last_slot = slot
        poll_due = now - last_poll > POLL_INTERVAL
        overdue = now - last_poll > POLL_INTERVAL * 3

        if (poll_due and at_boundary or overdue) and check_wifi():
            new_state = fetch_display_state(state)
            if new_state.get("reboot"):
                print("Reboot requested by server")
                time.sleep(1)
                machine.reset()
            msg = new_state.get("message", "")
            if msg and msg != last_message:
                priority_until = now + SCREEN_SECONDS   # pop a new message up promptly
            last_message = msg
            state = new_state
            sync_tick = now_ticks
            last_poll = now

        # Design preview: when the server's anim_version changes, fetch the
        # preview animation immediately (version > 0) or restore the normal
        # animation (version back to 0).
        av = state.get("anim_version", 0)
        if av != last_anim_version and check_wifi():
            draw_status(["GETTING", "PREVIEW" if av else "ANIM"])
            if av:
                result = fetch_animation(SERVER_URL + "/firmware/preview.bin", secret=True)
            else:
                result = fetch_animation()
            if result != "OK":
                draw_status(["ANIM FAIL", result], COL_RED)
                time.sleep(2)
            last_anim_version = av
            last_anim_fetch = now
            current_anim_frame = -1

        # Refresh the animation hourly, but only if the schedule ever uses it
        # (and never while a preview is active — it would overwrite it).
        if check_wifi() and last_anim_version == 0 and ("ANIM" in state.get("allowed_modes", [])) and (now - last_anim_fetch > ANIM_REFRESH):
            draw_status(["GETTING", "ANIM"])
            result = fetch_animation()
            if result != "OK":
                draw_status(["ANIM FAIL", result], COL_RED)
                time.sleep(2)
            last_anim_fetch = now
            current_anim_frame = -1

        # Apply brightness from the schedule when it changes.
        if state["brightness"] != last_brightness:
            CURRENT_BRIGHTNESS = state["brightness"]
            BRIGHTNESS_LUT = bytearray([int(i * CURRENT_BRIGHTNESS) for i in range(256)])
            screen.reset_pens()
            ANIM["pens"] = None          # rebuild palette pens at new brightness
            current_anim_frame = -1
            last_brightness = state["brightness"]

        # If this device isn't paired yet, show its pair code and nothing else.
        if not state.get("paired", True):
            draw_pair_screen(state.get("pair_code", ""))
            i75.update()
            time.sleep(0.1)
            continue

        # Local clock, kept accurate from the server's time without needing NTP.
        if state["epoch"]:
            elapsed = time.ticks_diff(now_ticks, sync_tick) // 1000
            local_struct = time.localtime(state["epoch"] + state["tz_offset"] + elapsed)
        else:
            local_struct = time.localtime()

        # Build the cycle from the schedule's allowed modes, dropping any that
        # have nothing to show right now (no message / no animation file).
        allowed = state.get("allowed_modes", ["TRAINS", "WEATHER"])
        cycle = []
        for m in allowed:
            if m == "PHONE" and not state["message"]:
                continue
            if m == "ANIM" and not anim_available():
                continue
            cycle.append(m)
        if not cycle:
            cycle = ["CLOCK"]

        # A freshly-arrived message jumps to the front for SCREEN_SECONDS.
        if now < priority_until and state["message"] and "PHONE" in allowed:
            mode = "PHONE"
        else:
            mode = cycle[int(now // SCREEN_SECONDS) % len(cycle)]

        if mode == "ANIM" and last_mode != "ANIM":
            current_anim_frame = -1
        last_mode = mode

        if mode == "TRAINS":    draw_train_dashboard(state["trains"], now_ticks)
        elif mode == "WEATHER": draw_weather_3col(state["weather"], now_ticks)
        elif mode == "PHONE":   draw_phone_screen(state["message"], now_ticks)
        elif mode == "ANIM":    draw_animation(now_ticks)
        elif mode == "CLOCK":   draw_clock(local_struct)
        else:                   screen.clear()

        i75.update()
        time.sleep(0.02)


# No try/except here on purpose -- the bootloader handles crashes/rollback.
if __name__ == "__main__":
    main()

