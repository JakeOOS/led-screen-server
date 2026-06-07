# =====================================================================
#  SCREEN APP
# =====================================================================
#  This is the file you edit to change what the screen does.
#  It lives in TWO places, with IDENTICAL contents:
#    - on your SERVER repo as  device_app.py   (the source of truth)
#    - on the DEVICE as         app.py          (just the initial seed;
#                                                the bootloader overwrites it
#                                                from the server on updates)
#
#  To ship a change: edit device_app.py on GitHub, bump FIRMWARE_VERSION in
#  server.py, commit. The device picks it up on its next reboot.
#
#  NOTE: there is deliberately NO crash handler at the bottom -- the
#  bootloader catches crashes so it can roll back. Don't add one back.
# =====================================================================

import time
import network
import urequests
import interstate75
import machine
import gc

# --- CONFIG ---
WIFI_SSID = "SKYWI5D4"
WIFI_PASSWORD = "Jx14ShNK5u3YPH"
SERVER_URL = "https://led-screen-server.onrender.com"
DEVICE_ID = "tulsehill-01"
POLL_INTERVAL = 30          # seconds between server data polls
SCREEN_SECONDS = 15         # seconds each screen shows before the loop advances
ROTATION = ["TRAINS", "WEATHER"]   # add "PHONE" here later if you want messages in the loop

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
                "trains": trains,
                "weather": data.get("weather", []),
                "message": data.get("message", ""),
                "reboot": data.get("reboot", False),
            }
        else:
            print("Server status", r.status_code)
            r.close()
    except Exception as e:
        print("Server poll failed:", e)
    return current_state

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

# =====================================================================
# --- CORE LOOP ---
# =====================================================================
def main():
    connect_wifi()
    state = {"brightness": 0.6, "trains": [], "weather": [], "message": "", "reboot": False}
    last_poll = -9999
    last_brightness = -1
    global CURRENT_BRIGHTNESS

    while True:
        now = time.time()
        now_ticks = time.ticks_ms()

        if check_wifi() and (now - last_poll > POLL_INTERVAL):
            state = fetch_display_state(state)
            last_poll = now
            # Remote command: if the server says reboot, do it (this is how
            # you make the device pick up a new app version hands-free).
            if state.get("reboot"):
                print("Reboot requested by server")
                time.sleep(1)
                machine.reset()

        if state["brightness"] != last_brightness:
            CURRENT_BRIGHTNESS = state["brightness"]
            screen.reset_pens()
            last_brightness = state["brightness"]

        # Loop the screens locally on a smooth clock (independent of polling).
        mode = ROTATION[int(now // SCREEN_SECONDS) % len(ROTATION)]
        if mode == "TRAINS":    draw_train_dashboard(state["trains"], now_ticks)
        elif mode == "WEATHER": draw_weather_3col(state["weather"], now_ticks)
        elif mode == "PHONE":   draw_phone_screen(state["message"], now_ticks)
        else:                   screen.clear()

        i75.update()
        time.sleep(0.02)


# No try/except here on purpose: let crashes propagate so the bootloader
# can decide whether to roll back. Do not wrap this.
if __name__ == "__main__":
    main()

