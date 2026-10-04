# =====================================================================
#  SCREEN APP  (device_app.py in the repo, app.py on the device)
# =====================================================================
#  Standalone: the screen fetches its own data. No server, no accounts.
#    trains   -> Rail Data Marketplace, straight from the device
#    weather  -> OpenWeather, straight from the device
#    news     -> news.json, written hourly by a GitHub Action
#    anim     -> a .bin exported on the laptop and pushed to GitHub
#  WHICH of these show, when, and how bright comes from config.json in
#  the GitHub repo. Edit it there and the screen picks it up within a few
#  minutes. The last good copy is cached on flash for offline boots.
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
import json

# Must match "firmware" in config.json -- the bootloader refuses to install
# a download whose marker doesn't match the version it was told to fetch.
FW_VERSION = "33"

# --- CONFIG ---
# Secrets live in device_config.py, which is gitignored and flashed to the
# device separately — this file is public and is fetched over OTA, so
# nothing sensitive can sit in it. Copy device_config.example.py, fill it in,
# and put it on the device alongside app.py.
try:
    from device_config import WIFI_SSID, WIFI_PASSWORD, OWM_API_KEY, RDM_API_KEY
except ImportError:
    # No config on the device yet. Fail loud rather than silently running with
    # blank credentials and looping on a connection that can never succeed.
    raise RuntimeError(
        "device_config.py missing — copy device_config.example.py, fill in the "
        "WiFi credentials and API keys, and flash it alongside app.py")

REPO_RAW = "https://raw.githubusercontent.com/JakeOOS/led-screen-server"
CONFIG_URL = REPO_RAW + "/main/config.json"
WANIM_URL = REPO_RAW + "/main/weather_anims/"
NEWS_URL = REPO_RAW + "/data/news.json"      # written by .github/workflows/news.yml
RDM_URL = "https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepartureBoard/"
OWM_URL = "https://api.openweathermap.org/data/2.5/forecast?units=metric&cnt=16"

# Seconds between refreshes. At most one fetch runs per screen change, so a
# network stall lands between screens instead of freezing mid-animation.
CONFIG_REFRESH = 300
TRAINS_REFRESH = 60
WEATHER_REFRESH = 1800
NEWS_REFRESH = 900
CLOCK_REFRESH = 86400
ANIM_REFRESH = 3600          # re-download the animation at most once an hour
RETRY_SECONDS = 60           # wait this long after a failed fetch

FRAME_SIZE = 64 * 32 * 3

# Used until config.json has been fetched or read from the flash cache.
CFG = {
    "screen_seconds": 12,
    "lat": "51.5074", "lon": "-0.1278",
    "anim_url": "https://raw.githubusercontent.com/JakeOOS/TidBytTulse/main/anim.bin",
    "boards": [],
    "schedule": [{"from": 0, "brightness": 0.5, "screens": ["CLOCK"]}],
}

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
    '?': [" ### ", "   ##", "  ## ", "     ", "  ## "], '!': ["  ## ", "  ## ", "  ## ", "     ", "  ## "],
    '.': ["  ", "  ", "  ", "##", "##"], ',': ["  ", "  ", "  ", " ##", "## "],
    ':': ["##", "##", "  ", "##", "##"], "'": ["##", "##", "  ", "  ", "  "]
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

def wifi_up():
    return network.WLAN(network.STA_IF).isconnected()

def check_wifi():
    if not wifi_up(): return connect_wifi()
    return True

# =====================================================================
# --- CLOCK (NTP + UK daylight saving, worked out on the device) ---
# =====================================================================
CLOCK = {"ok": False}

def sync_clock():
    try:
        import ntptime
        ntptime.settime()            # sets the RTC to UTC
        CLOCK["ok"] = True
        return True
    except Exception as e:
        print("NTP failed:", e)
        return False

def _dow(y, m, d):
    """Day of week, 0 = Sunday."""
    t = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
    if m < 3:
        y -= 1
    return (y + y // 4 - y // 100 + y // 400 + t[m - 1] + d) % 7

def _is_bst(tm):
    """UK summer time runs from 01:00 UTC on the last Sunday of March to
    01:00 UTC on the last Sunday of October."""
    y, m, d, h = tm[0], tm[1], tm[2], tm[3]
    if m < 3 or m > 10:
        return False
    if 3 < m < 10:
        return True
    last_sun = 31 - _dow(y, m, 31)
    if m == 3:
        return d > last_sun or (d == last_sun and h >= 1)
    return d < last_sun or (d == last_sun and h < 1)

def uk_now():
    t = time.time()
    if _is_bst(time.gmtime(t)):
        t += 3600
    return time.gmtime(t)

# =====================================================================
# --- CONFIG (config.json in the GitHub repo, cached on flash) ---
# =====================================================================
CONFIG_CACHE = "config_cache.json"
_cfg_text = [""]

def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""

def _apply_config(text):
    cfg = json.loads(text)
    if not (isinstance(cfg, dict) and cfg.get("schedule")):
        raise ValueError("config has no schedule")
    CFG.update(cfg)

def load_cached_config():
    text = _read(CONFIG_CACHE)
    if not text:
        return False
    try:
        _apply_config(text)
        _cfg_text[0] = text
        return True
    except Exception as e:
        print("Cached config unusable:", e)
        return False

def fetch_config():
    try:
        gc.collect()
        r = urequests.get(CONFIG_URL + "?t=" + str(time.ticks_ms()), timeout=8)
        if r.status_code != 200:
            print("Config status", r.status_code)
            r.close()
            return False
        text = r.text.strip()
        r.close()
        _apply_config(text)
        if text != _cfg_text[0]:         # only touch flash when it changed
            _cfg_text[0] = text
            try:
                with open(CONFIG_CACHE, "w") as f:
                    f.write(text)
            except OSError:
                pass
        return True
    except Exception as e:
        print("Config fetch failed:", e)
        return False

def active_band(hour):
    """The schedule entry in force at this hour: the last one whose "from"
    has passed. Before the first entry's "from", the last entry carries on
    overnight."""
    bands = CFG.get("schedule") or []
    best = None
    for b in bands:
        if b.get("from", 0) <= hour:
            best = b
    return best or (bands[-1] if bands else {})

# =====================================================================
# --- LIVE DATA (fetched straight from the APIs) ---
# =====================================================================
DATA = {"stations": {}, "rev": 0, "weather": [], "news": ""}

def stream_items(raw, key, on_item):
    """Call on_item(dict) for each object in the JSON array at `key`, reading
    the response in small chunks. The rail and weather responses are tens of
    KB, far too big to parse whole on this board; one element at a time is
    under a KB. Returns how many items were delivered."""
    needle = b'"' + key + b'"'
    buf = b""
    started = False
    depth = 0
    in_str = False
    esc = False
    item = bytearray()
    count = 0
    while True:
        chunk = raw.read(512)
        if not chunk:
            break
        if not started:
            buf += chunk
            i = buf.find(needle)
            if i < 0:
                buf = buf[-len(needle):]
                continue
            j = i + len(needle)
            while j < len(buf) and buf[j] in b" :\r\n\t":
                j += 1
            if j >= len(buf):
                buf = buf[i:]            # value starts in the next chunk
                continue
            if buf[j] != 91:             # not "[" -- null, e.g. no services
                return 0
            chunk = buf[j + 1:]
            buf = b""
            started = True
        for b in chunk:
            if depth == 0:
                if b == 123:             # {
                    depth = 1
                    item = bytearray(b"{")
                elif b == 93:            # ] -- end of the array
                    return count
                continue
            item.append(b)
            if in_str:
                if esc:
                    esc = False
                elif b == 92:            # backslash
                    esc = True
                elif b == 34:            # "
                    in_str = False
            elif b == 34:
                in_str = True
            elif b == 123:
                depth += 1
            elif b == 125:               # }
                depth -= 1
                if depth == 0:
                    try:
                        on_item(json.loads(bytes(item)))
                        count += 1
                    except Exception as e:
                        print("Bad item:", e)
                    item = bytearray()
    return count

def station_codes():
    out = []
    for b in CFG.get("boards", []):
        s = b.get("station")
        if s and s not in out:
            out.append(s)
    return out

def _hhmm(s):
    try:
        return int(s[0:2]) * 60 + int(s[3:5])
    except Exception:
        return -1

def fetch_station(crs):
    """Departures from one station, kept as (destination, minute-of-day,
    colour). minute-of-day is None for a cancelled service."""
    wanted = []
    for b in CFG.get("boards", []):
        if b.get("station") == crs:
            wanted.extend(b.get("match", []))
    out = []

    def on_item(t):
        try:
            dest = t["destination"][0]["locationName"]
        except Exception:
            return
        if len(out) >= 24 or not any(x in dest for x in wanted):
            return
        std = t.get("std") or ""
        etd = t.get("etd") or ""
        if etd == "Cancelled":
            out.append((dest, None, COL_RED))
        elif ":" in etd:
            out.append((dest, _hhmm(etd), COL_ORANGE))
        elif etd == "Delayed":
            out.append((dest, _hhmm(std), COL_ORANGE))
        else:
            out.append((dest, _hhmm(std), COL_GREEN))

    try:
        gc.collect()
        r = urequests.get(RDM_URL + crs, timeout=8, headers={
            "x-apikey": RDM_API_KEY, "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"})
        if r.status_code != 200:
            print("RDM", crs, "status", r.status_code)
            r.close()
            return False
        try:
            stream_items(r.raw, b"trainServices", on_item)
        finally:
            r.close()
        DATA["stations"][crs] = out
        DATA["rev"] += 1
        return True
    except Exception as e:
        print("RDM error", crs, e)
        return False

def build_trains(now_min):
    """Rows for draw_train_dashboard. Minutes are counted from the device's
    own clock, so they keep ticking down between fetches."""
    rows = []
    for b in CFG.get("boards", []):
        match = b.get("match", [])
        times = []
        for dest, when, col in DATA["stations"].get(b.get("station"), ()):
            if not any(x in dest for x in match):
                continue
            if when is None:
                times.append({"text": "CNCL", "color": col})
            elif when >= 0:
                diff = when - now_min
                if diff < -1000:
                    diff += 24 * 60
                if diff < -1:
                    continue
                times.append({"text": "NOW" if diff <= 0 else "%dM" % diff,
                              "color": col})
            if len(times) >= 6:
                break
        rows.append({"badge": b.get("badge", "?"),
                     "badge_col": tuple(b.get("badge_col", COL_GREY)),
                     "times": times})
    return rows

def fetch_weather():
    """Today and tomorrow: high, low and a condition for the animated clip."""
    days = {}
    order = []

    def on_item(item):
        stamp = item["dt_txt"]
        date_str = stamp[0:10]
        hour = int(stamp[11:13])
        if date_str not in days:
            days[date_str] = {"temps": [], "icons": []}
            order.append(date_str)
        d = days[date_str]
        d["temps"].append(item["main"]["temp"])
        if 6 <= hour <= 21:
            cond = item["weather"][0]["main"].lower()
            if "rain" in cond or "drizzle" in cond:
                d["icons"].append("rain")
            elif "snow" in cond:
                d["icons"].append("snow")
            elif "thunder" in cond:
                d["icons"].append("thunderstorm")
            else:
                # OWM calls 11-25% coverage "Clouds" ("few clouds"),
                # which reads as a sunny day. Judge by actual coverage.
                pct = (item.get("clouds") or {}).get("all", 100)
                d["icons"].append("clear" if pct <= 40 else "clouds")

    try:
        gc.collect()
        url = OWM_URL + "&lat=%s&lon=%s&appid=%s" % (
            CFG.get("lat"), CFG.get("lon"), OWM_API_KEY)
        r = urequests.get(url, timeout=8)
        if r.status_code != 200:
            print("OWM status", r.status_code)
            r.close()
            return False
        try:
            stream_items(r.raw, b"list", on_item)
        finally:
            r.close()
        out = []
        for date_str in order[:2]:
            dd = days[date_str]
            icons = dd["icons"] or ["clouds"]
            if icons.count("rain") >= 2:
                mapped = "rain"
            else:
                non_rain = [c for c in icons if c != "rain"] or icons
                mapped = non_rain[0]
                for c in non_rain:
                    if non_rain.count(c) > non_rain.count(mapped):
                        mapped = c
            out.append({"high": round(max(dd["temps"])),
                        "low": round(min(dd["temps"])), "icon_name": mapped})
        if not out:
            return False
        DATA["weather"] = out
        return True
    except Exception as e:
        print("OWM error", e)
        return False

def fetch_news():
    try:
        gc.collect()
        r = urequests.get(NEWS_URL + "?t=" + str(time.ticks_ms()), timeout=8)
        if r.status_code != 200:
            print("News status", r.status_code)
            r.close()
            return False
        DATA["news"] = str(r.json().get("text", ""))
        r.close()
        return True
    except Exception as e:
        print("News fetch failed:", e)
        return False

def wanted_jobs(screens):
    """(name, refresh seconds) for everything the current schedule needs."""
    jobs = [("clock", CLOCK_REFRESH)]
    if "TRAINS" in screens:
        for crs in station_codes():
            jobs.append(("trains:" + crs, TRAINS_REFRESH))
    if "WEATHER" in screens:
        jobs.append(("weather", WEATHER_REFRESH))
    if "NEWS" in screens:
        jobs.append(("news", NEWS_REFRESH))
    jobs.append(("config", CONFIG_REFRESH))
    return jobs

def run_job(name):
    if name == "clock":   return sync_clock()
    if name == "config":  return fetch_config()
    if name == "weather": return fetch_weather()
    if name == "news":    return fetch_news()
    return fetch_station(name[7:])       # "trains:XXX"

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

def fetch_animation(url, dest="anim.bin"):
    """Download a .bin to dest, being careful with limited flash. Returns a
    short status string: 'OK', 'HTTP nnn', 'FULL nn' (disk), 'BAD SIZE', or
    'ERR n'."""
    print("Fetching animation... free:", free_bytes())
    gc.collect()
    tmp = dest + ".tmp"
    # Clear any half-written temp from a previous failed attempt.
    try: os.remove(tmp)
    except OSError: pass
    try:
        r = urequests.get(url + "?t=" + str(time.ticks_ms()), timeout=20)
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
        # old copy first to make room (this is what beats error 28).
        if expected:
            fb = free_bytes()
            if 0 <= fb < expected + 20000:        # 20KB safety margin
                try: os.remove(dest)
                except OSError: pass
                gc.collect()
            fb = free_bytes()
            if 0 <= fb < expected + 20000:        # still won't fit
                r.close()
                return "FULL %d" % (expected // 1024)

        written = 0
        try:
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.raw.read(512)
                    if not chunk: break
                    f.write(chunk)
                    written += len(chunk)
        finally:
            r.close()

        size_ok = (expected is None) or (written == expected)
        if size_ok and _validate_anim(tmp, written):
            try: os.remove(dest)
            except OSError: pass
            os.rename(tmp, dest)
            if dest == "anim.bin":
                ANIM["loaded"] = False    # force header/palette reload
            print("Animation updated:", dest, written, "bytes")
            return "OK"
        print("Bad anim download:", written, "bytes")
        try: os.remove(tmp)
        except OSError: pass
        return "BAD SIZE"
    except OSError as e:
        try: os.remove(tmp)
        except OSError: pass
        return "ERR %s" % (e.args[0] if e.args else "?")
    except Exception as e:
        try: os.remove(tmp)
        except OSError: pass
        print("Anim fetch error:", e)
        return "ERR"

# =====================================================================
# --- WEATHER-SCREEN ANIMATION ---
# =====================================================================
# One full-frame 64x32 clip showing today's condition; the temps and a
# short divider are overlaid on top. Clips live in the repo
# (weather_anims/); the device refetches when the forecast condition changes.
# No snow clip exists yet, so snow borrows the rain one.
WEATHER_ANIM_CONDS = {"clear": "sunny", "clouds": "cloudy", "rain": "rain",
                      "thunderstorm": "stormy", "snow": "rain"}
WANIM = {
    "L": {"path": "wthr_L.bin", "x": 0, "cond": "", "loaded": False,
          "pens": None, "cur": -1},
}
WSTATE = {"drawn": False, "last_try": -9999}


def _wanim_load_conds():
    """Restore which condition the on-flash clip holds (survives reboot)."""
    cond = _read("wthr_meta.txt").split(",")[-1]
    if cond:
        WANIM["L"]["cond"] = cond


def _wanim_save_conds():
    try:
        with open("wthr_meta.txt", "w") as f:
            f.write(WANIM["L"]["cond"])
    except OSError:
        pass


def _wanim_load(slot):
    """Read a side's LDA1 header + palette into its slot."""
    sl = WANIM[slot]
    sl["loaded"] = False
    sl["pens"] = None
    try:
        with open(sl["path"], "rb") as f:
            head = f.read(10)
            if len(head) < 10 or head[0:4] != b"LDA1":
                return False
            ncolors = head[6] | (head[7] << 8)
            sl.update(w=head[4], h=head[5], ncolors=ncolors,
                      nframes=head[8] | (head[9] << 8),
                      offset=10 + ncolors * 3, fbytes=head[4] * head[5],
                      pal=f.read(ncolors * 3), loaded=True)
        return True
    except OSError:
        return False


def _wanim_pens(slot):
    sl = WANIM[slot]
    lut = BRIGHTNESS_LUT
    pal = sl["pal"]
    cp = graphics.create_pen
    sl["pens"] = [cp(lut[pal[i*3]], lut[pal[i*3+1]], lut[pal[i*3+2]])
                  for i in range(sl["ncolors"])]


def _wanim_draw(slot, ref_ticks):
    """Draw this side's current frame. Returns True if a new frame drew."""
    sl = WANIM[slot]
    if not sl["loaded"] and not _wanim_load(slot):
        return False
    nf = sl["nframes"]
    if nf <= 0:
        return False
    fi = (ref_ticks // 100) % nf
    if fi == sl["cur"]:
        return False
    try:
        with open(sl["path"], "rb") as f:
            f.seek(sl["offset"] + fi * sl["fbytes"])
            data = f.read(sl["fbytes"])
    except OSError:
        sl["loaded"] = False
        return False
    sl["cur"] = fi
    if sl["pens"] is None:
        _wanim_pens(slot)
    pens = sl["pens"]
    set_pen = graphics.set_pen
    pixel = graphics.pixel
    x0 = sl["x"]; w = sl["w"]; h = sl["h"]
    idx = 0
    for y in range(h):
        for x in range(w):
            set_pen(pens[data[idx]])
            pixel(x0 + x, y)
            idx += 1
    return True


def _text_w(s, font, spacing=1):
    w = 0
    for ch in str(s).upper():
        g = font.get(ch)
        w += (len(g[0]) if g else 3) + spacing
    return w - spacing if w else 0


def draw_weather_split(data, ref_ticks):
    """Today's condition animates across the full frame. Temp block at the
    bottom right: today's high/low left of a short divider, tomorrow's
    right of it. The divider is only as tall as the two text rows."""
    if not data:
        screen.clear()
        screen.text("WEATHER...", 5, 12, COL_WHITE, font=FONT_3X5)
        return
    drew = _wanim_draw("L", ref_ticks)
    if not (drew or not WSTATE["drawn"]):
        return                      # nothing changed on screen
    if not WSTATE["drawn"]:
        screen.clear()              # first draw after entering the mode
    WSTATE["drawn"] = True

    # Temp rows: high at y=18, low at y=25 (1px off the bottom edge).
    # Divider spans exactly the text block: y=18..30.
    graphics.set_pen(screen.create_pen(COL_WHITE))
    graphics.line(52, 18, 52, 31)

    today = data[0]
    tom = data[1] if len(data) > 1 else None
    # One empty column each side of the divider: today ends at x=50,
    # line at x=52, tomorrow starts at x=54.
    hi = str(today.get("high", "")); lo = str(today.get("low", ""))
    screen.text(hi, 51 - _text_w(hi, FONT_4X6), 18, COL_RED, font=FONT_4X6)
    screen.text(lo, 51 - _text_w(lo, FONT_4X6), 25, COL_BLUE, font=FONT_4X6)
    if tom:
        screen.text(str(tom.get("high", "")), 54, 18, COL_RED, font=FONT_4X6)
        screen.text(str(tom.get("low", "")), 54, 25, COL_BLUE, font=FONT_4X6)


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

def draw_voxel_loader(lit, failed_indices=None):
    """Draw VOXEL centred on screen.
    V = internal boot   O = wifi + clock   X = config   E = live data   L = ready
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
    any stage failed. errors = list of short strings e.g. ['WIFI FAIL']."""
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
    rows = min(3, len(dashboard_data))
    for i in range(rows):
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
    for i in range(rows):
        train_row = dashboard_data[i]
        y = y_offsets[i]
        graphics.set_pen(screen.create_pen(train_row['badge_col']))
        graphics.rectangle(0, y, 17, 10)
        screen.text(train_row['badge'], 2, y + 3, COL_BLACK, font=FONT_3X5)
        if i < 2:
            graphics.set_pen(screen.create_pen(COL_GREY))
            graphics.line(0, y + 10, 64, y + 10)

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

def draw_news_screen(text, ref_time):
    """Red NEWS header + the current story in the 4x6 font, scrolling
    vertically when it doesn't fit the area below the header."""
    screen.clear()
    if text:
        lines = wrap_text_to_lines(text, max_w=62)
        area_top = 9
        area_h = 32 - area_top
        total_h = len(lines) * 7 - 1
        if total_h <= area_h:
            y = area_top + (area_h - total_h) // 2
        else:
            ms_per_pixel = 150
            distance = total_h - area_h
            scroll_time = distance * ms_per_pixel
            cycle = scroll_time + 2000
            t = ref_time % cycle
            y = area_top - (t // ms_per_pixel if t < scroll_time else distance)
        for line in lines:
            if -7 <= y < 32:
                screen.text(line, 1, y, COL_WHITE, font=FONT_BOLD_5X5, spacing=1)
            y += 7
    # Header drawn last so scrolled lines pass underneath it.
    graphics.set_pen(screen.create_pen(COL_BLACK))
    graphics.rectangle(0, 0, 64, 8)
    screen.text("NEWS", 1, 1, COL_RED, font=FONT_3X5)
    graphics.set_pen(screen.create_pen(COL_GREY))
    graphics.line(0, 7, 64, 7)


def draw_clock(local_struct):
    screen.clear()
    hh = "%02d" % local_struct[3]
    mm = "%02d" % local_struct[4]
    screen.text(hh + ":" + mm, 5, 5, COL_WHITE, font=FONT_TALL_5X11, scale=2, spacing=2)

# =====================================================================
# --- CORE LOOP ---
# =====================================================================
def main():
    global CURRENT_BRIGHTNESS, BRIGHTNESS_LUT, current_anim_frame
    print("Boot free bytes:", free_bytes())
    _wanim_load_conds()   # which weather clip is already on flash
    load_cached_config()
    # What the bootloader installed, and what it gave up on. Used further
    # down to decide whether config.json is asking for a firmware update.
    installed_fw = _read("version.txt")
    bad_fw = _read("bad_version.txt")

    due = {}              # job name -> when it should next run

    def attempt(name, interval):
        ok = run_job(name)
        due[name] = time.time() + (interval if ok else RETRY_SECONDS)
        return ok

    # --- VOXEL boot loader -------------------------------------------
    # V = internal boot   O = wifi + clock   X = config   E = live data   L = ready
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
        if 0 < rem <= LETTER_MIN:        # the clock sync can jump time.time()
            time.sleep(rem)

    # V — internal boot (always succeeds if we got here)
    draw_voxel_loader(0)
    t = time.time()
    wait_min(t)
    light(True)

    # O — wifi, then the clock (retry a few times: WiFi may still be
    # settling right after boot)
    t = time.time()
    online = False
    clock_ok = False
    for _ in range(3):
        online = check_wifi()
        clock_ok = online and attempt("clock", CLOCK_REFRESH)
        if clock_ok:
            break
        time.sleep(2)
    wait_min(t)
    light(clock_ok, None if clock_ok else ("CLOCK FAIL" if online else "WIFI FAIL"))

    # X — config.json from GitHub (the flash copy carries on if this fails)
    t = time.time()
    have_cfg = online and attempt("config", CONFIG_REFRESH)
    wait_min(t)
    light(have_cfg, None if have_cfg else "CONFIG FAIL")

    # E — live data, but only what the schedule is showing right now
    t = time.time()
    api_ok = online
    if online:
        screens = active_band(uk_now()[3]).get("screens") or []
        for name, interval in wanted_jobs(screens):
            if name in ("clock", "config"):
                continue
            if not attempt(name, interval) and name != "news":
                api_ok = False
                label = "WEATHER FAIL" if name == "weather" else "TRAINS FAIL"
                if label not in errors:
                    errors.append(label)
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

    boot_ticks = time.ticks_ms()
    fw_armed = False
    last_anim_fetch = -9999
    last_wifi_try = -9999
    last_brightness = -1
    last_mode = ""
    last_slot = -1
    last_min = -1
    last_rev = -1
    trains = []
    cycle = ["CLOCK"]

    while True:
        now = time.time()
        now_ticks = time.ticks_ms()
        tm = uk_now()
        band = active_band(tm[3])
        screens = band.get("screens") or ["CLOCK"]
        screen_seconds = max(3, int(CFG.get("screen_seconds", 12)))

        # All network work happens on a screen-change boundary so any stall
        # lands between screens instead of freezing mid-animation.
        slot = int(now // screen_seconds)
        at_boundary = slot != last_slot
        last_slot = slot

        online = False
        if at_boundary:
            if wifi_up():
                online = True
            elif now - last_wifi_try > RETRY_SECONDS:
                last_wifi_try = now
                online = connect_wifi()

        if online:
            # At most one data fetch per boundary: the first that's due.
            for name, interval in wanted_jobs(screens):
                if now >= due.get(name, 0):
                    gc.collect()         # give TLS the biggest contiguous block we can
                    attempt(name, interval)
                    break

            # Firmware: config.json names the version that should be running.
            # If it isn't the one installed (and isn't one the bootloader
            # already rolled back from), reboot so the bootloader fetches it.
            # Not in the first 5 minutes, so GitHub's cache can't cause a
            # reboot loop while it still serves the old file.
            if not fw_armed and time.ticks_diff(now_ticks, boot_ticks) > 300000:
                fw_armed = True
            want_fw = str(CFG.get("firmware", ""))
            if fw_armed and want_fw and installed_fw and want_fw not in (installed_fw, bad_fw):
                print("Firmware", want_fw, "requested; rebooting to update")
                draw_status(["UPDATING"])
                time.sleep(1)
                machine.reset()

            # Refresh the animation hourly, but only while the schedule uses it.
            if "ANIM" in screens and (now - last_anim_fetch > ANIM_REFRESH):
                draw_status(["GETTING", "ANIM"])
                result = fetch_animation(CFG.get("anim_url", ""))
                if result != "OK":
                    draw_status(["ANIM FAIL", result], COL_RED)
                    time.sleep(2)
                last_anim_fetch = now
                current_anim_frame = -1

            # Weather clip: refetch when today's forecast condition changes.
            wx = DATA["weather"]
            if "WEATHER" in screens and wx and (now - WSTATE["last_try"] > 300):
                want = WEATHER_ANIM_CONDS.get(wx[0].get("icon_name", ""), "")
                sl = WANIM["L"]
                if want and want != sl["cond"]:
                    WSTATE["last_try"] = now
                    res = fetch_animation(WANIM_URL + want + "_L.bin", dest=sl["path"])
                    if res == "OK":
                        sl["cond"] = want
                        sl["loaded"] = False
                        sl["cur"] = -1
                        WSTATE["drawn"] = False
                        _wanim_save_conds()
                    elif res.startswith("HTTP"):
                        # Clip not in the repo (yet) — stop retrying
                        # until the condition changes.
                        sl["cond"] = want
                        _wanim_save_conds()
                    else:
                        print("Weather anim fetch", want, res)

        # Apply brightness from the schedule when it changes.
        brightness = band.get("brightness", 0.5)
        if brightness != last_brightness:
            CURRENT_BRIGHTNESS = brightness
            BRIGHTNESS_LUT = bytearray([int(i * CURRENT_BRIGHTNESS) for i in range(256)])
            screen.reset_pens()
            ANIM["pens"] = None          # rebuild palette pens at new brightness
            WANIM["L"]["pens"] = None
            WANIM["L"]["cur"] = -1
            WSTATE["drawn"] = False
            current_anim_frame = -1
            last_brightness = brightness

        # Train countdowns only change on the minute or when new data lands.
        now_min = tm[3] * 60 + tm[4]
        if now_min != last_min or DATA["rev"] != last_rev:
            last_min = now_min
            last_rev = DATA["rev"]
            trains = build_trains(now_min) if DATA["stations"] else []

        # Build the cycle from the schedule's screens, dropping any that
        # have nothing to show right now (no news / no animation file).
        if at_boundary:
            cycle = []
            for m in screens:
                if m == "ANIM" and not anim_available():
                    continue
                if m == "NEWS" and not DATA["news"]:
                    continue
                cycle.append(m)
            if not cycle:
                cycle = ["CLOCK"]

        mode = cycle[slot % len(cycle)]

        if mode == "ANIM" and last_mode != "ANIM":
            current_anim_frame = -1
        if mode == "WEATHER" and last_mode != "WEATHER":
            WSTATE["drawn"] = False
            WANIM["L"]["cur"] = -1
        last_mode = mode

        if mode == "TRAINS":    draw_train_dashboard(trains, now_ticks)
        elif mode == "WEATHER": draw_weather_split(DATA["weather"], now_ticks)
        elif mode == "NEWS":    draw_news_screen(DATA["news"], now_ticks)
        elif mode == "ANIM":    draw_animation(now_ticks)
        elif mode == "CLOCK":   draw_clock(tm)
        else:                   screen.clear()

        i75.update()
        time.sleep(0.02)


# No try/except here on purpose -- the bootloader handles crashes/rollback.
if __name__ == "__main__":
    main()
