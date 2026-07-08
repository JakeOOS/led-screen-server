"""Live desktop preview of the LED screen -- runs device_app.py's real renderer
functions, unmodified, and shows the 64x32 output in a window.

Usage:
    python3 sim/simulate.py                 # sample data
    python3 sim/simulate.py --live          # poll the real server for live data

Keys: 1 trains  2 weather  3 message  4 clock  5 anim   r  force-reload device_app.py
Saving device_app.py auto-reloads it, so edits show up within a second.
"""

import argparse
import importlib
import os
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import fakehw  # noqa: E402

fakehw.install()

import device_app  # noqa: E402

PIXEL = 10   # size of one simulated LED, in screen px
GAP = 2      # subtle black gap between LEDs, in screen px
CELL = PIXEL + GAP
MARGIN = 4
GRID_W, GRID_H = 64, 32

MODE_KEYS = {"1": "TRAINS", "2": "WEATHER", "3": "PHONE", "4": "CLOCK", "5": "ANIM"}

SAMPLE_TRAINS = [
    {"badge": "LBG", "badge_col": (0, 150, 255),
     "times": [{"text": "2", "color": (255, 255, 255)}, {"text": "9", "color": (255, 255, 255)},
               {"text": "17", "color": (255, 255, 255)}]},
    {"badge": "CST", "badge_col": (255, 140, 0),
     "times": [{"text": "5", "color": (255, 255, 255)}, {"text": "22", "color": (255, 255, 255)}]},
    {"badge": "VIC", "badge_col": (0, 200, 100),
     "times": [{"text": "1", "color": (255, 80, 80)}, {"text": "14", "color": (255, 255, 255)}]},
]
SAMPLE_WEATHER = [
    {"day": "MON", "icon_name": "clear", "low": 12, "high": 21},
    {"day": "TUE", "icon_name": "rain", "low": 10, "high": 16},
    {"day": "WED", "icon_name": "clouds", "low": 9, "high": 15},
]
SAMPLE_MESSAGE = "HAPPY BIRTHDAY"


def rgb_hex(rgb):
    return "#%02x%02x%02x" % rgb


class Simulator:
    def __init__(self, root, live):
        self.root = root
        self.live = live
        self.mode = "WEATHER"
        self.server_state = None
        self.last_poll = 0.0
        self.device_path = device_app.__file__
        self.last_mtime = os.path.getmtime(self.device_path)
        self.prev_buf = [[None] * GRID_W for _ in range(GRID_H)]

        win_w = MARGIN * 2 + GRID_W * CELL
        win_h = MARGIN * 2 + GRID_H * CELL
        self.canvas = tk.Canvas(root, width=win_w, height=win_h, bg="black", highlightthickness=0)
        self.canvas.pack()

        self.ids = [[None] * GRID_W for _ in range(GRID_H)]
        for y in range(GRID_H):
            for x in range(GRID_W):
                x0 = MARGIN + x * CELL
                y0 = MARGIN + y * CELL
                self.ids[y][x] = self.canvas.create_rectangle(
                    x0, y0, x0 + PIXEL, y0 + PIXEL, fill="black", outline=""
                )

        root.bind("<Key>", self.on_key)
        self.tick()

    def on_key(self, event):
        if event.char in MODE_KEYS:
            self.mode = MODE_KEYS[event.char]
        elif event.char == "r":
            self.reload_device_app()

    def reload_device_app(self):
        global device_app
        device_app = importlib.reload(device_app)
        self.device_path = device_app.__file__
        self.last_mtime = os.path.getmtime(self.device_path)
        print("[sim] reloaded device_app.py")

    def maybe_autoreload(self):
        try:
            mtime = os.path.getmtime(self.device_path)
        except OSError:
            return
        if mtime != self.last_mtime:
            self.last_mtime = mtime
            self.reload_device_app()

    def maybe_poll_server(self):
        if self.live and (time.time() - self.last_poll > 15):
            self.server_state = device_app.fetch_display_state(self.server_state)
            self.last_poll = time.time()

    def draw_current_mode(self, now_ticks):
        state = self.server_state
        if self.mode == "TRAINS":
            data = state["trains"] if (state and state.get("trains")) else SAMPLE_TRAINS
            device_app.draw_train_dashboard(data, now_ticks)
        elif self.mode == "WEATHER":
            data = state["weather"] if (state and state.get("weather")) else SAMPLE_WEATHER
            device_app.draw_weather_split(data, now_ticks)
        elif self.mode == "PHONE":
            msg = state["message"] if (state and state.get("message")) else SAMPLE_MESSAGE
            device_app.draw_phone_screen(msg, now_ticks)
        elif self.mode == "CLOCK":
            device_app.draw_clock(time.localtime())
        elif self.mode == "ANIM":
            device_app.draw_animation(now_ticks)

    def render(self):
        buf = device_app.i75.display.buf
        for y in range(GRID_H):
            row = buf[y]
            prev_row = self.prev_buf[y]
            id_row = self.ids[y]
            for x in range(GRID_W):
                c = row[x]
                if c != prev_row[x]:
                    self.canvas.itemconfig(id_row[x], fill=rgb_hex(c))
                    prev_row[x] = c

    def tick(self):
        self.maybe_autoreload()
        self.maybe_poll_server()
        self.draw_current_mode(int(time.time() * 1000))
        device_app.i75.update()
        self.render()
        self.root.after(33, self.tick)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="poll the real server for live data")
    args = parser.parse_args()

    root = tk.Tk()
    root.title("VOXEL screen simulator -- 1-5 mode, r reload")
    Simulator(root, args.live)
    root.mainloop()


if __name__ == "__main__":
    main()
