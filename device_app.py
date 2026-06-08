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

FONT_BOLD_5X5 = {
    'A': [" ### ", "## ##", "#####", "## ##", "## ##"], 'B': ["#### ", "## ##", "#### ", "## ##", "#### "],
    'C': [" ####", "##   ", "##   ", "##   ", " ####"], 'D': ["###  ", "## ##", "## ##", "###  ", "###  "],
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
SUN_F1 = ["                ", "       YYYYYY    ", "     YYYYYYYYYY  ", "  YYYYYYYYYYYY  ", "  YYYYYYYYYYYY  ", " YYYYYYYYYYYYYY ", " YYYYYYYYYYYYYY ", " YYYYYYYYYYYYYY ", " YYYYYYYYYYYYYY ", "  YYYYYYYYYYYY  ", "  YYYYYYYYYYYY  ", "     YYYYYYYYYY  ", "       YYYYYY    ", "                "]
SUN_F2 = ["        YYYY     ", "     YYYYYYYYYY  ", "  YYYYYYYYYYYY  ", " YYYYYYYYYYYYYY ", " YYYYYYYYYYYYYY ", " YYYYYYYYYYYYYY ", "YYYYYYYYYYYYYYYY", "YYYYYYYYYYYYYYYY", " YYYYYYYYYYYYYY ", " YYYYYYYYYYYYYY ", " YYYYYYYYYYYYYY ", "  YYYYYYYYYYYY  ", "     YYYYYYYYYY  ", "        YYYY     "]
CLOUD_F1 = ["                ", "                ", "       WWWWWW    ", "     WWWWWWWWWW  ", " WWWWWWWWWWWWWW ", "WWWWWWWWWWWWWWWW", "WWWWWWWWWWWWWWWW", "WWWWWWWWWWWWWWWW", " WWWWWWWWWWWWWW ", "                ", "                ", "                ", "                ", "                "]
CLOUD_F2 = ["                ", "       WWWWWW    ", "     WWWWWWWWWW  ", " WWWWWWWWWWWWWW ", "WWWWWWWWWWWWWWWW", "WWWWWWWWWWWWWWWW", "WWWWWWWWWWWWWWWW", " WWWWWWWWWWWWWW ", "                ", "                ", "                ", "                ", "                ", "                "]
RAIN_F1 = ["                ", "       WWWWWW    ", "     WWWWWWWWWW  ", " WWWWWWWWWWWWWW ", " GGGGGGGGGGGGGG ", " GGGGGGGGGGGGGG ", "                ", "  CC   CC   CC  ", "  CC   CC   CC  ", "                ", "    CC   CC     ", "    CC   CC     ", "                ", "                "]
RAIN_F2 = ["                ", "       WWWWWW    ", "     WWWWWWWWWW  ", " WWWWWWWWWWWWWW ", " GGGGGGGGGGGGGG ", " GGGGGGGGGGGGGG ", "                ", "    CC   CC     ", "    CC   CC     ", "                ", "  CC   CC   CC  ", "  CC   CC   CC  ", "                ", "                "]
WEATHER_MAP = {'clear': (SUN_F1, SUN_F2), 'clouds': (CLOUD_F1, CLOUD_F2), 'rain': (RAIN_F1, RAIN_F2)}

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
        r = urequests.get(url, timeout=10)
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
        return os.stat("anim.bin")[6] >= FRAME_SIZE
    except OSError:
        return False

def free_bytes():
    try:
        s = os.statvfs("/")
        return s[0] * s[3]
    except Exception:
        return -1

def fetch_animation():
    """Download the .bin, being careful with limited flash. Returns a short
    status string: 'OK', 'HTTP nnn', 'FULL nn' (disk), 'BAD SIZE', or 'ERR n'."""
    print("Fetching animation... free:", free_bytes())
    gc.collect()
    # Clear any half-written temp from a previous failed attempt.
    try: os.remove("anim.tmp")
    except OSError: pass
    try:
        r = urequests.get(ANIM_URL + "?t=" + str(time.ticks_ms()), timeout=20)
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

        valid = written > 0 and (written % FRAME_SIZE == 0)
        if expected is not None:
            valid = valid and (written == expected)
        if valid:
            try: os.remove("anim.bin")
            except OSError: pass
            os.rename("anim.tmp", "anim.bin")
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

def draw_animation(ref_ticks):
    global current_anim_frame
    try:
        with open("anim.bin", "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()
            if file_size < FRAME_SIZE:
                return
            num_frames = file_size // FRAME_SIZE
            frame_idx = (ref_ticks // 100) % num_frames
            if frame_idx == current_anim_frame:
                return
            current_anim_frame = frame_idx
            f.seek(frame_idx * FRAME_SIZE)
            frame_data = f.read(FRAME_SIZE)
            set_pen = graphics.set_pen
            create_pen = graphics.create_pen
            pixel = graphics.pixel
            lut = BRIGHTNESS_LUT
            idx = 0
            for y in range(32):
                for x in range(64):
                    set_pen(create_pen(lut[frame_data[idx]], lut[frame_data[idx + 1]], lut[frame_data[idx + 2]]))
                    pixel(x, y)
                    idx += 3
    except OSError:
        screen.clear()
        screen.text("NO ANIM", 16, 14, COL_RED, font=FONT_3X5)

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
    anim_frame = (ref_ticks // 400) % 2
    for i, day in enumerate(data):
        if i > 2: break
        x_base = col_starts[i]
        frames = WEATHER_MAP.get(day['icon_name'], WEATHER_MAP['clouds'])
        screen.draw_pixel_icon(frames[anim_frame], x_base + 2, 1)
        text_w = len(day['day']) * 4 - 1
        text_x = x_base + (21 - text_w) // 2
        screen.text(day['day'], text_x, 18, COL_CYAN, font=FONT_3X5)
        high_str, low_str = str(day['high']), str(day['low'])
        total_w = (len(low_str) * 4 - 1) + 2 + (len(high_str) * 4 - 1)
        start_x = x_base + (21 - total_w) // 2
        screen.text(low_str, start_x, 25, COL_BLUE, font=FONT_3X5)
        screen.text(high_str, start_x + (len(low_str) * 4 - 1) + 2, 25, COL_RED, font=FONT_3X5)

def get_word_width(word):
    w = 0
    for c in word:
        w += len(FONT_BOLD_5X5.get(c, ["     "][0])) + 1
    return w

def wrap_text_to_lines(text, max_w=62):
    words = text.split(" ")
    lines = []
    current_line = ""
    for word in words:
        if not word: continue
        current_w = get_word_width(current_line + " " + word) if current_line else get_word_width(word)
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

def draw_phone_screen(msg, ref_time):
    screen.clear()
    if not msg:
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
             "epoch": 0, "tz_offset": 0}

    # Boot checklist: each row ticks green as it completes.
    steps = [["WIFI", "pending"], ["WEATHER", "pending"], ["TRAINS", "pending"]]
    draw_checklist(steps)

    steps[0][1] = "active"; draw_checklist(steps)
    wifi_ok = connect_wifi()
    steps[0][1] = "done" if wifi_ok else "fail"; draw_checklist(steps)
    time.sleep(0.3)

    # A single server poll returns both weather and trains; reveal them in turn.
    steps[1][1] = "active"; draw_checklist(steps)
    state = fetch_display_state(state)
    steps[1][1] = "done" if state.get("weather") else "fail"; draw_checklist(steps)
    time.sleep(0.4)

    steps[2][1] = "active"; draw_checklist(steps)
    time.sleep(0.3)
    steps[2][1] = "done" if state.get("trains") else "fail"; draw_checklist(steps)
    time.sleep(0.6)

    sync_tick = time.ticks_ms()
    last_poll = time.time()        # we already polled above; don't re-poll instantly
    last_anim_fetch = -9999
    last_brightness = -1
    last_message = ""
    last_mode = ""
    priority_until = 0
    global CURRENT_BRIGHTNESS, BRIGHTNESS_LUT, current_anim_frame

    while True:
        now = time.time()
        now_ticks = time.ticks_ms()

        if check_wifi() and (now - last_poll > POLL_INTERVAL):
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

        # Refresh the animation hourly, but only if the schedule ever uses it.
        if check_wifi() and ("ANIM" in state.get("allowed_modes", [])) and (now - last_anim_fetch > ANIM_REFRESH):
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
            current_anim_frame = -1
            last_brightness = state["brightness"]

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
