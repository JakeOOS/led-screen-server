"""
TidByt-style LED screen — control server (LIVE DATA VERSION).

Same endpoints as the dummy, so your device firmware needs NO changes.
The only difference: trains/weather now come from Rail Data Marketplace and
OpenWeather instead of the fake functions.

Key points:
- API keys are read from ENVIRONMENT VARIABLES, never hardcoded. This matters
  because Render reads your code from GitHub; a key committed to a public repo
  is a leaked key.
- Data is CACHED server-side (trains ~60s, weather ~30min) and shared across all
  devices, so 1 device or 100 devices makes the same number of upstream calls.
- "Minutes until departure" is computed in Europe/London time on the server, so
  it's correct no matter what timezone the cloud host runs in.

Run locally:
    pip install -r requirements.txt
    set OWM_API_KEY=...      (Windows)   /   export OWM_API_KEY=...   (Mac/Linux)
    set RDM_API_KEY=...
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

import requests
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# --- Secrets (set these as environment variables; do NOT paste keys here) ---
OWM_API_KEY = os.environ.get("OWM_API_KEY", "")
RDM_API_KEY = os.environ.get("RDM_API_KEY", "")

# --- Location / board config (this becomes per-device settings later) -------
OWM_LAT = "51.5074"
OWM_LON = "-0.1278"

RDM_URL_BASE = "https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepartureBoard/"
UK_TZ = ZoneInfo("Europe/London")

# Each board = one row on the screen. Same logic you had in the firmware,
# just expressed as data so it's easy to add/edit stations later.
BOARDS = [
    {"badge": "TLK", "badge_col": [150, 0, 0],  "station": "TUH",
     "match": ["St Albans", "Luton", "Bedford", "Farringdon", "Elephant & Castle"]},
    {"badge": "LBG", "badge_col": [0, 200, 50], "station": "TUH",
     "match": ["London Bridge"]},
    {"badge": "VIC", "badge_col": [0, 150, 200], "station": "WDU",
     "match": ["Victoria"]},
]

# =====================================================================
# --- Device config store (unchanged from dummy) ---
# =====================================================================
DEVICE_CONFIG = {}
DEFAULT_CONFIG = {"brightness": 0.6, "mode": "TRAINS", "message": "HELLO FROM THE SERVER"}


def get_config(device_id: str):
    if device_id not in DEVICE_CONFIG:
        DEVICE_CONFIG[device_id] = dict(DEFAULT_CONFIG)
    return DEVICE_CONFIG[device_id]


# =====================================================================
# --- TRAINS (Rail Data Marketplace) ---
# =====================================================================
_station_cache = {}          # station_code -> {"ts": float, "services": [...]}
STATION_TTL = 60             # seconds


def _fetch_station(station: str):
    """Fetch one station's board, cached. On failure, keep last good data."""
    now = time.time()
    cached = _station_cache.get(station)
    if cached and (now - cached["ts"] < STATION_TTL):
        return cached["services"]
    services = cached["services"] if cached else []
    try:
        r = requests.get(RDM_URL_BASE + station,
                         headers={"x-apikey": RDM_API_KEY, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
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
    if diff < -1000:          # crossed midnight
        diff += 24 * 60
    return diff


def _parse_service(t):
    std = t.get("std")
    etd = t.get("etd")
    color = [0, 255, 0]               # green = on time
    if etd == "Cancelled":
        return {"text": "CNCL", "color": [255, 50, 50]}
    check_time = std
    if etd and ":" in etd:            # a revised time
        check_time = etd
        color = [255, 140, 0]         # orange = delayed-but-expected
    elif etd == "Delayed":
        color = [255, 140, 0]
    mins = _minutes_until(check_time)
    if mins < -1:                     # already gone
        return None
    return {"text": "NOW" if mins <= 0 else f"{mins}M", "color": color}


def get_trains():
    if not RDM_API_KEY:
        print("WARNING: RDM_API_KEY not set — serving placeholder trains.")
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
# --- WEATHER (OpenWeather 5-day / 3-hour forecast) ---
# =====================================================================
_weather_cache = {"ts": 0, "data": []}
WEATHER_TTL = 1800           # 30 minutes


def get_weather():
    now = time.time()
    if _weather_cache["data"] and (now - _weather_cache["ts"] < WEATHER_TTL):
        return _weather_cache["data"]
    if not OWM_API_KEY:
        print("WARNING: OWM_API_KEY not set — serving placeholder weather.")
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
            if 6 <= hour <= 21:          # daytime slots only set the icon
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
# --- Endpoints (identical to the dummy) ---
# =====================================================================
@app.get("/api/device/{device_id}/display")
def get_display(device_id: str):
    cfg = get_config(device_id)
    return {
        "brightness": cfg["brightness"],
        "mode": cfg["mode"],
        "trains": get_trains(),
        "weather": get_weather(),
        "message": cfg["message"],
        "server_time": int(time.time()),
    }


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
    return {"status": "ok",
            "rdm_key_set": bool(RDM_API_KEY),
            "owm_key_set": bool(OWM_API_KEY),
            "devices": list(DEVICE_CONFIG.keys())}

@app.get("/debug/rdm/{station}")
def debug_rdm(station: str):
    r = requests.get(RDM_URL_BASE + station,
                     headers={"x-apikey": RDM_API_KEY, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    return {
        "status": r.status_code,
        "key_len": len(RDM_API_KEY),
        "key_tail": RDM_API_KEY[-4:] if RDM_API_KEY else None,
        "body": r.text[:600],
    }
