"""
LED screen control server (LIVE DATA + OTA + SCHEDULE + PERSISTENT CONFIG).

Per-device config (train boards + schedule + messages) is stored in Supabase so
it SURVIVES restarts. The device API shape is unchanged, so no device update is
needed for this step. Pairing is added in a later step on top of this.

Required environment variables (set in Render):
  OWM_API_KEY    OpenWeather key
  RDM_API_KEY    Rail Data Marketplace key
  SUPABASE_URL   e.g. https://abcd1234.supabase.co
  SUPABASE_KEY   the service_role key (Project Settings -> API)

If SUPABASE_URL/KEY are absent, the server falls back to in-memory storage with
default config, so it still runs (just without persistence).
"""

import os
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, List

import requests
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel

app = FastAPI()

FIRMWARE_VERSION = "10"        # bumped: device gains a pairing screen

OWM_API_KEY = os.environ.get("OWM_API_KEY", "")
RDM_API_KEY = os.environ.get("RDM_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

OWM_LAT = "51.5074"
OWM_LON = "-0.1278"
RDM_URL_BASE = "https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepartureBoard/"
UK_TZ = ZoneInfo("Europe/London")
RDM_HEADERS = {"x-apikey": RDM_API_KEY, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
MESSAGE_TTL = 3600

# --- Defaults for a brand-new device (your current Tulse Hill setup) --------
DEFAULT_BOARDS = [
    {"badge": "TLK", "badge_col": [150, 0, 0],  "station": "TUH",
     "match": ["St Albans", "Luton", "Bedford", "Farringdon", "Elephant & Castle"]},
    {"badge": "LBG", "badge_col": [0, 200, 50], "station": "TUH",
     "match": ["London Bridge"]},
    {"badge": "VIC", "badge_col": [0, 150, 200], "station": "WDU",
     "match": ["Victoria"]},
]
# Schedule = list of bands. The band whose 'start' hour is the latest one <= now
# (London time) is active. brightness 0..1, modes is which screens may show.
DEFAULT_SCHEDULE = [
    {"start": 5,  "brightness": 1.0, "modes": ["TRAINS", "WEATHER", "PHONE"]},
    {"start": 12, "brightness": 0.5, "modes": ["TRAINS", "WEATHER", "PHONE", "ANIM", "CLOCK"]},
    {"start": 19, "brightness": 0.2, "modes": ["PHONE", "ANIM", "CLOCK"]},
    {"start": 0,  "brightness": 0.2, "modes": ["TRAINS", "WEATHER", "PHONE", "ANIM", "CLOCK"]},
]

# =====================================================================
# --- Persistence layer (Supabase REST, with in-memory fallback) ---
# =====================================================================
SB_DEVICES = (SUPABASE_URL + "/rest/v1/devices") if SUPABASE_URL else ""
SB_HEADERS = {"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY,
              "Content-Type": "application/json"}
_MEM = {}   # fallback store when Supabase isn't configured


def _gen_code():
    return "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))


def _new_device(device_id):
    return {"device_id": device_id, "name": "", "paired": False, "pair_code": _gen_code(),
            "config": {"boards": DEFAULT_BOARDS, "schedule": DEFAULT_SCHEDULE},
            "message": "", "message_ts": 0, "reboot": False, "last_seen": int(time.time())}


def get_device(device_id):
    """Fetch a device row, creating it with defaults if it doesn't exist yet."""
    if not SB_DEVICES:
        if device_id not in _MEM:
            _MEM[device_id] = _new_device(device_id)
        return _MEM[device_id]
    try:
        r = requests.get(SB_DEVICES + "?device_id=eq." + device_id + "&select=*",
                         headers=SB_HEADERS, timeout=8)
        if r.status_code == 200:
            rows = r.json()
            if rows:
                return rows[0]
    except Exception as e:
        print("Supabase get error:", e)
        return _new_device(device_id)      # transient: serve defaults, don't crash
    # not found -> create it
    row = _new_device(device_id)
    try:
        h = dict(SB_HEADERS); h["Prefer"] = "resolution=merge-duplicates,return=representation"
        r = requests.post(SB_DEVICES, headers=h, json=row, timeout=8)
        if r.status_code in (200, 201):
            d = r.json()
            return d[0] if d else row
    except Exception as e:
        print("Supabase create error:", e)
    return row


def save_device(device_id, fields):
    """Persist a partial update (dict of column -> value)."""
    if not SB_DEVICES:
        if device_id in _MEM:
            _MEM[device_id].update(fields)
        return
    try:
        h = dict(SB_HEADERS); h["Prefer"] = "return=minimal"
        requests.patch(SB_DEVICES + "?device_id=eq." + device_id,
                       headers=h, json=fields, timeout=8)
    except Exception as e:
        print("Supabase save error:", e)


def current_message(dev):
    msg = dev.get("message", "")
    if msg and (time.time() - (dev.get("message_ts") or 0) > MESSAGE_TTL):
        return ""
    return msg


def schedule_for(dev):
    sched = (dev.get("config") or {}).get("schedule") or DEFAULT_SCHEDULE
    h = datetime.now(UK_TZ).hour
    best = None
    for band in sched:
        s = band.get("start", 0)
        if s <= h and (best is None or s > best.get("start", -1)):
            best = band
    if best is None:                       # before the earliest band -> wrap to latest
        best = max(sched, key=lambda b: b.get("start", 0))
    return best.get("brightness", 0.5), best.get("modes", ["TRAINS", "WEATHER"])


def uk_tz_offset_seconds():
    off = datetime.now(UK_TZ).utcoffset()
    return int(off.total_seconds()) if off else 0


# =====================================================================
# --- TRAINS ---
# =====================================================================
_station_cache = {}
STATION_TTL = 60


def _fetch_station(station):
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


def _minutes_until(hhmm):
    if not hhmm or ":" not in hhmm:
        return 999
    now = datetime.now(UK_TZ)
    cur = now.hour * 60 + now.minute
    h, m = map(int, hhmm.split(":"))
    diff = (h * 60 + m) - cur
    if diff < -1000:
        diff += 24 * 60
    return diff


def _parse_service(t):
    std = t.get("std"); etd = t.get("etd")
    color = [0, 255, 0]
    if etd == "Cancelled":
        return {"text": "CNCL", "color": [255, 50, 50]}
    check = std
    if etd and ":" in etd:
        check = etd; color = [255, 140, 0]
    elif etd == "Delayed":
        color = [255, 140, 0]
    mins = _minutes_until(check)
    if mins < -1:
        return None
    return {"text": "NOW" if mins <= 0 else f"{mins}M", "color": color}


def get_trains(boards):
    if not RDM_API_KEY:
        return [{"badge": b["badge"], "badge_col": b["badge_col"],
                 "times": [{"text": "--", "color": [80, 80, 80]}]} for b in boards]
    out = []
    for b in boards:
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
        out.append({"badge": b["badge"], "badge_col": b["badge_col"], "times": times})
    return out


# =====================================================================
# --- WEATHER (shared; per-device location is a later step) ---
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
            label = "TDY" if i == 0 else ("TMR" if i == 1 else
                     ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"][datetime.strptime(order[i], "%Y-%m-%d").weekday()])
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
    dev = get_device(device_id)
    reboot = bool(dev.get("reboot"))
    fields = {"last_seen": int(time.time())}
    if reboot:
        fields["reboot"] = False         # one-shot
    save_device(device_id, fields)
    if not dev.get("paired", False):
        return {
            "paired": False,
            "pair_code": dev.get("pair_code", ""),
            "brightness": 0.5,
            "allowed_modes": ["PAIR"],
            "trains": [], "weather": [], "message": "",
            "reboot": reboot,
            "epoch": int(time.time()),
            "tz_offset": uk_tz_offset_seconds(),
            "server_time": int(time.time()),
        }
    bright, allowed = schedule_for(dev)
    boards = (dev.get("config") or {}).get("boards") or DEFAULT_BOARDS
    return {
        "paired": True,
        "brightness": bright,
        "allowed_modes": allowed,
        "trains": get_trains(boards),
        "weather": get_weather(),
        "message": current_message(dev),
        "reboot": reboot,
        "epoch": int(time.time()),
        "tz_offset": uk_tz_offset_seconds(),
        "server_time": int(time.time()),
    }


class ConfigUpdate(BaseModel):
    message: Optional[str] = None
    reboot: Optional[bool] = None
    name: Optional[str] = None
    boards: Optional[list] = None
    schedule: Optional[list] = None


@app.post("/api/device/{device_id}/config")
def update_config(device_id: str, update: ConfigUpdate):
    dev = get_device(device_id)
    fields = {}
    if update.message is not None:
        fields["message"] = update.message
        fields["message_ts"] = int(time.time())
    if update.reboot is not None:
        fields["reboot"] = update.reboot
    if update.name is not None:
        fields["name"] = update.name
    if update.boards is not None or update.schedule is not None:
        cfg = dev.get("config") or {}
        if update.boards is not None:
            cfg["boards"] = update.boards
        if update.schedule is not None:
            cfg["schedule"] = update.schedule
        fields["config"] = cfg
    if fields:
        save_device(device_id, fields)
    return {"ok": True, "device_id": device_id}


class PairBody(BaseModel):
    code: str
    name: Optional[str] = None


def find_device_by_code(code):
    code = (code or "").strip().upper()
    if not code:
        return None
    if not SB_DEVICES:
        for d in _MEM.values():
            if d.get("pair_code", "").upper() == code and not d.get("paired"):
                return d
        return None
    try:
        # ilike = case-insensitive match in Supabase/PostgREST
        r = requests.get(
            SB_DEVICES + "?pair_code=ilike." + code + "&paired=eq.false&select=*",
            headers=SB_HEADERS, timeout=8)
        if r.status_code == 200:
            rows = r.json()
            return rows[0] if rows else None
    except Exception as e:
        print("Supabase find error:", e)
    return None


@app.post("/api/pair")
def pair_device(body: PairBody):
    dev = find_device_by_code(body.code)
    if not dev:
        return {"ok": False, "error": "Invalid or already-used code"}
    fields = {"paired": True}
    if body.name:
        fields["name"] = body.name
    save_device(dev["device_id"], fields)
    return {"ok": True, "device_id": dev["device_id"], "name": body.name or dev.get("name", "")}


# =====================================================================
# --- Firmware (OTA) + control page ---
# =====================================================================
@app.get("/firmware/version")
def firmware_version():
    return {"version": FIRMWARE_VERSION}


@app.get("/firmware/app")
def firmware_app():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "device_app.py")) as f:
            return PlainTextResponse(f.read())
    except OSError:
        return PlainTextResponse("# device_app.py not found", status_code=404)


@app.get("/app")
def control_panel():
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, "control.html")) as f:
            return HTMLResponse(f.read())
    except OSError:
        return HTMLResponse("<h1>control.html not found</h1>", status_code=404)


@app.get("/")
def root():
    return {"status": "ok",
            "firmware_version": FIRMWARE_VERSION,
            "rdm_key_set": bool(RDM_API_KEY),
            "owm_key_set": bool(OWM_API_KEY),
            "persistence": "supabase" if SB_DEVICES else "in-memory (NOT persistent)",
            "devices_in_memory": list(_MEM.keys())}

