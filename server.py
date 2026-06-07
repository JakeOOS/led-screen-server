"""
TidByt-style LED screen — minimal control server (DUMMY VERSION).

The device polls  GET /api/device/{device_id}/display  every ~30s and gets back
everything it needs to render: brightness, which mode to show, and the data for
each screen. Right now the train/weather data is FAKE so you can prove the loop
end-to-end. Later you swap the fake_* functions for your real OWM / RDM calls
(the logic already works in your firmware — just move it up here).

Your phone app will eventually POST to /api/device/{device_id}/config to change
what's shown. For now you can do that with curl (see the README notes).

Run locally:
    pip install fastapi "uvicorn[standard]"
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

import time
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# --- In-memory device state (swap for a real DB / Supabase later) ----------
# Keyed by device_id. This IS your "what should the screen show" store.
DEVICE_CONFIG = {}

DEFAULT_CONFIG = {
    "brightness": 0.6,
    "mode": "TRAINS",                 # TRAINS | WEATHER | PHONE | OFF
    "message": "HELLO FROM THE SERVER",
}


def get_config(device_id: str):
    if device_id not in DEVICE_CONFIG:
        DEVICE_CONFIG[device_id] = dict(DEFAULT_CONFIG)
    return DEVICE_CONFIG[device_id]


# --- FAKE DATA -------------------------------------------------------------
# Replace these two functions with your real Rail Data Marketplace / OpenWeather
# calls. Keep the SHAPE identical and the firmware needs no changes.
# Colors are [r, g, b] lists; the device converts them to tuples on receipt.

def fake_trains():
    return [
        {"badge": "TLK", "badge_col": [150, 0, 0], "times": [
            {"text": "3M",  "color": [0, 255, 0]},
            {"text": "11M", "color": [0, 255, 0]},
            {"text": "22M", "color": [255, 140, 0]},
        ]},
        {"badge": "LBG", "badge_col": [0, 200, 50], "times": [
            {"text": "NOW", "color": [0, 255, 0]},
            {"text": "14M", "color": [0, 255, 0]},
        ]},
        {"badge": "VIC", "badge_col": [0, 150, 200], "times": [
            {"text": "6M",   "color": [0, 255, 0]},
            {"text": "CNCL", "color": [255, 50, 50]},
        ]},
    ]


def fake_weather():
    return [
        {"day": "TDY", "high": 12, "low": 5, "icon_name": "clouds"},
        {"day": "TMR", "high": 14, "low": 7, "icon_name": "clear"},
        {"day": "WED", "high": 10, "low": 4, "icon_name": "rain"},
    ]


# --- What the device polls -------------------------------------------------
@app.get("/api/device/{device_id}/display")
def get_display(device_id: str):
    cfg = get_config(device_id)
    return {
        "brightness": cfg["brightness"],
        "mode": cfg["mode"],
        "trains": fake_trains(),
        "weather": fake_weather(),
        "message": cfg["message"],
        "server_time": int(time.time()),
    }


# --- What your phone app will POST to (test it with curl for now) ----------
class ConfigUpdate(BaseModel):
    brightness: Optional[float] = None
    mode: Optional[str] = None
    message: Optional[str] = None


@app.post("/api/device/{device_id}/config")
def update_config(device_id: str, update: ConfigUpdate):
    cfg = get_config(device_id)
    if update.brightness is not None:
        cfg["brightness"] = update.brightness
    if update.mode is not None:
        cfg["mode"] = update.mode.upper()
    if update.message is not None:
        cfg["message"] = update.message
    return cfg


@app.get("/")
def root():
    return {"status": "ok", "devices": list(DEVICE_CONFIG.keys())}
