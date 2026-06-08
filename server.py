"""
LED screen control server (LIVE DATA + OTA + SCHEDULE).

The SCHEDULE lives here on purpose: it's the policy your phone app will edit
later. The device just obeys whatever this returns.

Schedule (Europe/London time):
  05:00-12:00  brightness 1.0   trains, weather, messages
  12:00-19:00  brightness 0.5   everything
  19:00-00:00  brightness 0.2   messages, animation, clock
  00:00-05:00  brightness 0.2   everything

To ship a new device app: edit device_app.py, bump FIRMWARE_VERSION, commit,
then reboot the device (power cycle, or POST {"reboot": true} to its config).
"""

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

import requests
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel

app = FastAPI()

FIRMWARE_VERSION = "6"        # bump this whenever device_app.py changes

OWM_API_KEY = os.environ.get("OWM_API_KEY", "")
RDM_API_KEY = os.environ.get("RDM_API_KEY", "")

OWM_LAT = "51.5074"
OWM_LON = "-0.1278"

RDM_URL_BASE = "https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepartureBoard/"
UK_TZ = ZoneInfo("Europe/London")
RDM_HEADERS = {"x-apikey": RDM_API_KEY, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}

MESSAGE_TTL = 3600            # messages auto-clear after 1 hour

BOARDS = [
    {"badge": "TLK", "badge_col": [150, 0, 0],  "station": "TUH",
     "match": ["St Albans", "Luton", "Bedford", "Farringdon", "Elephant & Castle"]},
    {"badge": "LBG", "badge_col": [0, 200, 50], "station": "TUH",
     "match": ["London Bridge"]},
    {"badge": "VIC", "badge_col": [0, 150, 200], "station": "WDU",
     "match": ["Victoria"]},
]

# =====================================================================
# --- Schedule (this is what the phone app will eventually control) ---
# =====================================================================
def get_schedule():
    """Return (brightness, allowed_modes) for the current London time."""
    h = datetime.now(UK_TZ).hour
    if 5 <= h < 12:
        return 1.0, ["TRAINS", "WEATHER", "PHONE"]
    if 12 <= h < 19:
        return 0.5, ["TRAINS", "WEATHER", "PHONE", "ANIM", "CLOCK"]
    if 19 <= h < 24:
        return 0.2, ["PHONE", "ANIM", "CLOCK"]
    return 0.2, ["TRAINS", "WEATHER", "PHONE", "ANIM", "CLOCK"]   # 00:00-05:00


def uk_tz_offset_seconds():
    off = datetime.now(UK_TZ).utcoffset()
    return int(off.total_seconds()) if off else 0


# =====================================================================
# --- Device config store ---
# =====================================================================
DEVICE_CONFIG = {}
DEFAULT_CONFIG = {"message": "", "message_ts": 0, "reboot": False}


def get_config(device_id: str):
    if device_id not in DEVICE_CONFIG:
        DEVICE_CONFIG[device_id] = dict(DEFAULT_CONFIG)
    return DEVICE_CONFIG[device_id]


def current_message(cfg):
    msg = cfg.get("message", "")
    if msg and (time.time() - cfg.get("message_ts", 0) > MESSAGE_TTL):
        return ""               # expired
    return msg


# =====================================================================
# --- TRAINS ---
# =====================================================================
_station_cache = {}
STATION_TTL = 60


def _fetch_station(station: str):
    now = time.time()
    cached = _station_cache.get(station)
    if cached and (now - cached["ts"] < STATION_TTL):
        return cached["services"]
    services = cached["services"] if cached else []
    try:
        r = requests.get(RDM_URL_BASE + station, headers=RDM_HEADERS, timeout=10)
        if r.status_code == 200:
            services = r.json().get("trainServices") or []
        else:
            print("RDM", station, "status", r.status_code)
    except Exception as e:
        print("RDM error", station, e)
    _station_cache[station] = {"ts": now, "services": services}
    return services


def _minutes_until(hhmm: str) -> int:
    if not hhmm or ":" not in hhmm:
        return 999
    now = datetime.now(UK_TZ)
    current = now.hour * 60 + now.minute
    h, m = map(int, hhmm.split(":"))
    diff = (h * 60 + m) - current
    if diff < -1000:
        diff += 24 * 60
    return diff


def _parse_service(t):
    std = t.get("std")
    etd = t.get("etd")
    color = [0, 255, 0]
    if etd == "Cancelled":
        return {"text": "CNCL", "color": [255, 50, 50]}
    check_time = std
    if etd and ":" in etd:
        check_time = etd
        color = [255, 140, 0]
    elif etd == "Delayed":
        color = [255, 140, 0]
    mins = _minutes_until(check_time)
    if mins < -1:
        return None
    return {"text": "NOW" if mins <= 0 else f"{mins}M", "color": color}


def get_trains():
    if not RDM_API_KEY:
        return [{"badge": b["badge"], "badge_col": b["badge_col"],
                 "times": [{"text": "--", "color": [80, 80, 80]}]} for b in BOARDS]
    boards = []
    for b in BOARDS:
        services = _fetch_station(b["station"])
        times = []
        for t in services:
            try:
                dest = t["destination"][0]["locationName"]
            except Exception:
                continue
            if any(x in dest for x in b["match"]):
                item = _parse_service(t)
                if item:
                    times.append(item)
                if len(times) >= 6:
                    break
        boards.append({"badge": b["badge"], "badge_col": b["badge_col"], "times": times})
    return boards


# =====================================================================
# --- WEATHER ---
# =====================================================================
_weather_cache = {"ts": 0, "data": []}
WEATHER_TTL = 1800


def get_weather():
    now = time.time()
    if _weather_cache["data"] and (now - _weather_cache["ts"] < WEATHER_TTL):
        return _weather_cache["data"]
    if not OWM_API_KEY:
        return [{"day": "TDY", "high": 0, "low": 0, "icon_name": "clouds"}]
    try:
        url = (f"https://api.openweathermap.org/data/2.5/forecast"
               f"?lat={OWM_LAT}&lon={OWM_LON}&appid={OWM_API_KEY}&units=metric")
        data = requests.get(url, timeout=10).json()
        days, order = {}, []
        for item in data["list"]:
            date_str, time_str = item["dt_txt"].split(" ")
            hour = int(time_str.split(":")[0])
            if date_str not in days:
                days[date_str] = {"temps": [], "icons": []}
                order.append(date_str)
            d = days[date_str]
            d["temps"].append(item["main"]["temp"])
            if 6 <= hour <= 21:
                cond = item["weather"][0]["main"].lower()
                if "rain" in cond or "drizzle" in cond:
                    d["icons"].append("rain")
                elif "clear" in cond:
                    d["icons"].append("clear")
                else:
                    d["icons"].append("clouds")
        out = []
        for i in range(min(3, len(order))):
            dd = days[order[i]]
            high, low = round(max(dd["temps"])), round(min(dd["temps"]))
            icons = dd["icons"] or ["clouds"]
            if icons.count("rain") >= 2:
                mapped = "rain"
            else:
                non_rain = [c for c in icons if c != "rain"] or icons
                mapped = max(set(non_rain), key=non_rain.count)
            if i == 0:
                label = "TDY"
            elif i == 1:
                label = "TMR"
            else:
                wd = datetime.strptime(order[i], "%Y-%m-%d").weekday()
                label = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][wd]
            out.append({"day": label, "high": high, "low": low, "icon_name": mapped})
        _weather_cache["data"] = out
        _weather_cache["ts"] = now
        return out
    except Exception as e:
        print("OWM error", e)
        return _weather_cache["data"]


# =====================================================================
# --- Device endpoints ---
# =====================================================================
@app.get("/api/device/{device_id}/display")
def get_display(device_id: str):
    cfg = get_config(device_id)
    brightness, allowed = get_schedule()
    reboot = cfg.get("reboot", False)
    if reboot:
        cfg["reboot"] = False
    return {
        "brightness": brightness,
        "allowed_modes": allowed,
        "trains": get_trains(),
        "weather": get_weather(),
        "message": current_message(cfg),
        "reboot": reboot,
        "epoch": int(time.time()),
        "tz_offset": uk_tz_offset_seconds(),
        "server_time": int(time.time()),
    }


class ConfigUpdate(BaseModel):
    message: Optional[str] = None
    reboot: Optional[bool] = None


@app.post("/api/device/{device_id}/config")
def update_config(device_id: str, update: ConfigUpdate):
    cfg = get_config(device_id)
    if update.message is not None:
        cfg["message"] = update.message
        cfg["message_ts"] = time.time()      # start the 1-hour clock
    if update.reboot is not None:
        cfg["reboot"] = update.reboot
    return {"message": cfg["message"], "reboot": cfg["reboot"]}


# =====================================================================
# --- Firmware (OTA) endpoints ---
# =====================================================================
@app.get("/firmware/version")
def firmware_version():
    return {"version": FIRMWARE_VERSION}


@app.get("/firmware/app")
def firmware_app():
    try:
        with open("device_app.py") as f:
            return PlainTextResponse(f.read())
    except OSError:
        return PlainTextResponse("# device_app.py not found in repo", status_code=404)


@app.get("/app")
def control_panel():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "control.html")
    try:
        with open(path) as f:
            return HTMLResponse(f.read())
    except OSError:
        return HTMLResponse(
            "<h1>control.html not found</h1><p>Make sure control.html sits in "
            "the same folder as server.py at the repo root.</p>", status_code=404)


@app.get("/")
def root():
    bright, allowed = get_schedule()
    return {"status": "ok",
            "firmware_version": FIRMWARE_VERSION,
            "rdm_key_set": bool(RDM_API_KEY),
            "owm_key_set": bool(OWM_API_KEY),
            "now_brightness": bright,
            "now_allowed": allowed,
            "devices": list(DEVICE_CONFIG.keys())}
