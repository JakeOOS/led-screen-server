# Stand-ins for the MicroPython-only modules device_app.py imports (interstate75,
# machine, network, urequests), so the exact same rendering code can run on a
# desktop Python interpreter for the simulator in simulate.py.

import sys
import time
import types

import requests


def _patch_time():
    if not hasattr(time, "ticks_ms"):
        time.ticks_ms = lambda: int(time.time() * 1000)
    if not hasattr(time, "ticks_diff"):
        time.ticks_diff = lambda a, b: a - b


class FakeGraphics:
    """Mimics the Pimoroni `graphics` object: a 64x32 RGB pixel buffer."""

    def __init__(self, w=64, h=32):
        self.w, self.h = w, h
        self.buf = [[(0, 0, 0)] * w for _ in range(h)]
        self._pen = (0, 0, 0)

    def create_pen(self, r, g, b):
        return (r, g, b)

    def set_pen(self, pen):
        self._pen = pen

    def clear(self):
        p = self._pen
        for row in self.buf:
            for x in range(self.w):
                row[x] = p

    def pixel(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.buf[y][x] = self._pen

    def rectangle(self, x, y, w, h):
        for yy in range(y, y + h):
            if 0 <= yy < self.h:
                row = self.buf[yy]
                for xx in range(x, x + w):
                    if 0 <= xx < self.w:
                        row[xx] = self._pen

    def line(self, x0, y0, x1, y1):
        # device_app.py only ever draws axis-aligned lines.
        if x0 == x1:
            for y in range(min(y0, y1), max(y0, y1) + 1):
                self.pixel(x0, y)
        elif y0 == y1:
            for x in range(min(x0, x1), max(x0, x1) + 1):
                self.pixel(x, y0)


class FakeInterstate75:
    def __init__(self, display=None, panel_type=None):
        self.display = FakeGraphics()

    def update(self):
        pass  # the simulator reads self.display.buf directly after this call


def install():
    _patch_time()

    i75_mod = types.ModuleType("interstate75")
    i75_mod.Interstate75 = FakeInterstate75
    i75_mod.DISPLAY_INTERSTATE75_64X32 = "64x32"
    i75_mod.PANEL_FM6126A = "fm6126a"
    sys.modules["interstate75"] = i75_mod

    machine_mod = types.ModuleType("machine")
    machine_mod.reset = lambda: print("[sim] machine.reset() requested -- ignored")
    sys.modules["machine"] = machine_mod

    network_mod = types.ModuleType("network")
    network_mod.STA_IF = 0

    class WLAN:
        def __init__(self, mode):
            pass

        def active(self, *a):
            return True

        def isconnected(self):
            return True

        def connect(self, ssid, password):
            pass

    network_mod.WLAN = WLAN
    sys.modules["network"] = network_mod

    urequests_mod = types.ModuleType("urequests")

    class _Response:
        def __init__(self, r):
            self._r = r
            self.status_code = r.status_code
            self.headers = r.headers
            self.raw = r.raw

        def json(self):
            return self._r.json()

        def close(self):
            self._r.close()

    def get(url, headers=None, timeout=10):
        r = requests.get(url, headers=headers or {}, timeout=timeout, stream=True)
        return _Response(r)

    urequests_mod.get = get
    sys.modules["urequests"] = urequests_mod
