"""
LED screen control server — with Supabase Auth.

Three-layer content model:
  Screens    — atomic display configs (trains, weather, clock, message, animation)
  Catalogues — named playlists of screens, each with a play duration
  Schedule   — ordered stack of catalogues with end_hour; first starts at 00:00,
               each entry plays until its end_hour, last ends at midnight.

Security model:
  - Device polling (/api/device/.../display) uses a shared DEVICE_SECRET header.
  - All user-facing routes (/api/user/...) require a valid Supabase JWT.
  - The service_role key is only used for internal device/display polling.

Environment variables (set in Render):
  OWM_API_KEY   OpenWeather key
  RDM_API_KEY   Rail Data Marketplace key
  SUPABASE_URL  e.g. https://abcd1234.supabase.co
  SUPABASE_KEY  service_role key (Project Settings -> API)
  DEVICE_SECRET any long random string; flash it into main.py
"""

import os
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

import requests
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel

app = FastAPI()

FIRMWARE_VERSION = "22"

OWM_API_KEY   = os.environ.get("OWM_API_KEY", "")
RDM_API_KEY   = os.environ.get("RDM_API_KEY", "")
SUPABASE_URL  = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "")
DEVICE_SECRET = os.environ.get("DEVICE_SECRET", "")

OWM_LAT = "51.5074"
OWM_LON = "-0.1278"
RDM_URL_BASE = "https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepartureBoard/"
UK_TZ = ZoneInfo("Europe/London")
RDM_HEADERS = {
    "x-apikey": RDM_API_KEY,
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}
MESSAGE_TTL = 3600

DEFAULT_BOARDS = [
    {"badge": "TLK", "badge_col": [150, 0, 0],  "station": "TUH",
     "match": ["St Albans", "Luton", "Bedford", "Farringdon", "Elephant & Castle"]},
    {"badge": "LBG", "badge_col": [0, 200, 50], "station": "TUH",
     "match": ["London Bridge"]},
    {"badge": "VIC", "badge_col": [0, 150, 200], "station": "WDU",
     "match": ["Victoria"]},
]
DEFAULT_SCHEDULE = [
    {"start": 5,  "brightness": 1.0, "modes": ["TRAINS", "WEATHER", "PHONE"]},
    {"start": 12, "brightness": 0.5, "modes": ["TRAINS", "WEATHER", "PHONE", "ANIM", "CLOCK"]},
    {"start": 19, "brightness": 0.2, "modes": ["PHONE", "ANIM", "CLOCK"]},
    {"start": 0,  "brightness": 0.2, "modes": ["TRAINS", "WEATHER", "PHONE", "ANIM", "CLOCK"]},
]

BUILTIN_SCREENS = [
    {"name": "Morning trains", "type": "trains",
     "config": {"boards": DEFAULT_BOARDS}, "is_builtin": True},
    {"name": "Weather",        "type": "weather",    "config": {}, "is_builtin": True},
    {"name": "Clock",          "type": "clock",
     "config": {"color": [255, 255, 255], "format": "24h"}, "is_builtin": True},
    {"name": "Message board",  "type": "message",    "config": {"text": ""}, "is_builtin": True},
    {"name": "Animation",      "type": "animation",  "config": {"url": ""}, "is_builtin": True},
]

TYPE_MODES = {
    "trains":    "TRAINS",
    "weather":   "WEATHER",
    "clock":     "CLOCK",
    "message":   "PHONE",
    "animation": "ANIM",
}
VALID_TYPES = set(TYPE_MODES.keys())

# =====================================================================
# Auth helpers
# =====================================================================
SB_AUTH  = (SUPABASE_URL + "/auth/v1") if SUPABASE_URL else ""
SB_REST  = (SUPABASE_URL + "/rest/v1") if SUPABASE_URL else ""
SB_HEADERS_ADMIN = {
    "apikey": SUPABASE_KEY,
    "Authorization": "Bearer " + SUPABASE_KEY,
    "Content-Type": "application/json",
}
_MEM = {}


def verify_token(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization[7:]
    if not SB_AUTH:
        return {"id": "dev-user", "email": "dev@local"}
    try:
        r = requests.get(SB_AUTH + "/user",
                         headers={"Authorization": "Bearer " + token,
                                  "apikey": SUPABASE_KEY}, timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print("Auth verify error:", e)
    raise HTTPException(status_code=401, detail="Invalid or expired token")


def verify_device_secret(incoming):
    if DEVICE_SECRET and incoming != DEVICE_SECRET:
        raise HTTPException(status_code=401, detail={
            "error": "bad device secret",
            "got_length": len(incoming or ""),
            "expected_length": len(DEVICE_SECRET),
        })


# =====================================================================
# Device store
# =====================================================================
def _gen_code():
    return "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))


def _new_device(device_id):
    return {
        "device_id": device_id, "name": "", "paired": False,
        "owner_id": None, "pair_code": _gen_code(),
        "config": {"boards": DEFAULT_BOARDS, "schedule": DEFAULT_SCHEDULE},
        "message": "", "message_ts": 0, "reboot": False,
        "last_seen": int(time.time()),
    }


def _sb(path):
    return SB_REST + path


def get_device(device_id):
    if not SB_REST:
        if device_id not in _MEM:
            _MEM[device_id] = _new_device(device_id)
        return _MEM[device_id]
    try:
        r = requests.get(_sb("/devices?device_id=eq." + device_id + "&select=*"),
                         headers=SB_HEADERS_ADMIN, timeout=8)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception as e:
        print("Supabase get error:", e)
        return _new_device(device_id)
    row = _new_device(device_id)
    try:
        h = dict(SB_HEADERS_ADMIN)
        h["Prefer"] = "resolution=merge-duplicates,return=representation"
        r = requests.post(_sb("/devices"), headers=h, json=row, timeout=8)
        if r.status_code in (200, 201) and r.json():
            return r.json()[0]
    except Exception as e:
        print("Supabase create error:", e)
    return row


def save_device(device_id, fields):
    if not SB_REST:
        if device_id in _MEM:
            _MEM[device_id].update(fields)
        return
    try:
        h = dict(SB_HEADERS_ADMIN); h["Prefer"] = "return=minimal"
        requests.patch(_sb("/devices?device_id=eq." + device_id),
                       headers=h, json=fields, timeout=8)
    except Exception as e:
        print("Supabase save error:", e)


def find_device_by_code(code):
    code = (code or "").strip().upper()
    if not code:
        return None
    if not SB_REST:
        for d in _MEM.values():
            if d.get("pair_code", "").upper() == code and not d.get("paired"):
                return d
        return None
    try:
        r = requests.get(
            _sb("/devices?pair_code=ilike." + code + "&paired=eq.false&select=*"),
            headers=SB_HEADERS_ADMIN, timeout=8)
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception as e:
        print("Supabase find error:", e)
    return None


def get_user_devices(owner_id):
    if not SB_REST:
        return [d for d in _MEM.values() if d.get("owner_id") == owner_id]
    try:
        r = requests.get(_sb("/devices?owner_id=eq." + owner_id + "&select=*"),
                         headers=SB_HEADERS_ADMIN, timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print("Supabase list error:", e)
    return []


def current_message(dev):
    msg = dev.get("message", "")
    if msg and (time.time() - (dev.get("message_ts") or 0) > MESSAGE_TTL):
        return ""
    return msg


def legacy_schedule_for(dev):
    """Legacy fallback: read brightness+modes from flat config."""
    sched = (dev.get("config") or {}).get("schedule") or DEFAULT_SCHEDULE
    h = datetime.now(UK_TZ).hour
    best = None
    for band in sched:
        s = band.get("start", 0)
        if s <= h and (best is None or s > best.get("start", -1)):
            best = band
    if best is None:
        best = max(sched, key=lambda b: b.get("start", 0))
    return best.get("brightness", 0.5), best.get("modes", ["TRAINS", "WEATHER"])


def uk_tz_offset_seconds():
    off = datetime.now(UK_TZ).utcoffset()
    return int(off.total_seconds()) if off else 0


# =====================================================================
# Screens helpers (atomic display configs)
# =====================================================================
def get_screens(user_id=None):
    if not SB_REST:
        return [dict(s, id=str(i)) for i, s in enumerate(BUILTIN_SCREENS)]
    items = []
    try:
        r = requests.get(_sb("/screens?is_builtin=eq.true&select=*&order=created_at.asc"),
                         headers=SB_HEADERS_ADMIN, timeout=8)
        if r.status_code == 200:
            items.extend(r.json())
        if user_id:
            r = requests.get(
                _sb(f"/screens?owner_id=eq.{user_id}&is_builtin=eq.false"
                    f"&select=*&order=created_at.asc"),
                headers=SB_HEADERS_ADMIN, timeout=8)
            if r.status_code == 200:
                items.extend(r.json())
    except Exception as e:
        print("Screens get error:", e)
    return items


def create_screen(user_id, data):
    row = {
        "owner_id": user_id, "name": data["name"], "type": data["type"],
        "config": data.get("config", {}), "is_builtin": False, "is_public": False,
    }
    if not SB_REST:
        return dict(row, id="local-" + str(time.time()))
    try:
        h = dict(SB_HEADERS_ADMIN); h["Prefer"] = "return=representation"
        r = requests.post(_sb("/screens"), headers=h, json=row, timeout=8)
        if r.status_code in (200, 201) and r.json():
            return r.json()[0]
    except Exception as e:
        print("Screen create error:", e)
    return None


def update_screen(screen_id, user_id, data):
    if not SB_REST:
        return True
    try:
        h = dict(SB_HEADERS_ADMIN); h["Prefer"] = "return=minimal"
        r = requests.patch(
            _sb(f"/screens?id=eq.{screen_id}&owner_id=eq.{user_id}&is_builtin=eq.false"),
            headers=h, json=data, timeout=8)
        return r.status_code in (200, 204)
    except Exception as e:
        print("Screen update error:", e)
    return False


def delete_screen(screen_id, user_id):
    if not SB_REST:
        return True
    try:
        h = dict(SB_HEADERS_ADMIN)
        r = requests.delete(
            _sb(f"/screens?id=eq.{screen_id}&owner_id=eq.{user_id}&is_builtin=eq.false"),
            headers=h, timeout=8)
        return r.status_code in (200, 204)
    except Exception as e:
        print("Screen delete error:", e)
    return False


# =====================================================================
# Catalogue helpers (named playlists of screens)
# =====================================================================
def get_catalogue_screens(catalogue_id):
    """Return ordered screen slots for a catalogue."""
    if not SB_REST:
        return []
    try:
        r = requests.get(
            _sb(f"/catalogue_screens?catalogue_id=eq.{catalogue_id}"
                f"&select=*,screen:screens!screen_id(*)"
                f"&order=sort_order.asc"),
            headers=SB_HEADERS_ADMIN, timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print("Catalogue screens get error:", e)
    return []


def get_catalogues(user_id=None):
    if not SB_REST:
        return []
    items = []
    try:
        r = requests.get(_sb("/catalogues?is_builtin=eq.true&select=*&order=created_at.asc"),
                         headers=SB_HEADERS_ADMIN, timeout=8)
        if r.status_code == 200:
            items.extend(r.json())
        if user_id:
            r = requests.get(
                _sb(f"/catalogues?owner_id=eq.{user_id}&is_builtin=eq.false"
                    f"&select=*&order=created_at.asc"),
                headers=SB_HEADERS_ADMIN, timeout=8)
            if r.status_code == 200:
                items.extend(r.json())
        for cat in items:
            cat["screens"] = get_catalogue_screens(cat["id"])
    except Exception as e:
        print("Catalogues get error:", e)
    return items


def create_catalogue(user_id, name):
    row = {"owner_id": user_id, "name": name, "is_builtin": False}
    if not SB_REST:
        return dict(row, id="local-" + str(time.time()), screens=[])
    try:
        h = dict(SB_HEADERS_ADMIN); h["Prefer"] = "return=representation"
        r = requests.post(_sb("/catalogues"), headers=h, json=row, timeout=8)
        if r.status_code in (200, 201) and r.json():
            cat = r.json()[0]
            cat["screens"] = []
            return cat
    except Exception as e:
        print("Catalogue create error:", e)
    return None


def update_catalogue(catalogue_id, user_id, data):
    if not SB_REST:
        return True
    try:
        h = dict(SB_HEADERS_ADMIN); h["Prefer"] = "return=minimal"
        r = requests.patch(
            _sb(f"/catalogues?id=eq.{catalogue_id}&owner_id=eq.{user_id}&is_builtin=eq.false"),
            headers=h, json=data, timeout=8)
        return r.status_code in (200, 204)
    except Exception as e:
        print("Catalogue update error:", e)
    return False


def delete_catalogue(catalogue_id, user_id):
    if not SB_REST:
        return True
    try:
        h = dict(SB_HEADERS_ADMIN)
        r = requests.delete(
            _sb(f"/catalogues?id=eq.{catalogue_id}&owner_id=eq.{user_id}&is_builtin=eq.false"),
            headers=h, timeout=8)
        return r.status_code in (200, 204)
    except Exception as e:
        print("Catalogue delete error:", e)
    return False


def replace_catalogue_screens(catalogue_id, slots):
    """Replace all screen slots for a catalogue."""
    if not SB_REST:
        return True
    try:
        h = dict(SB_HEADERS_ADMIN)
        requests.delete(_sb(f"/catalogue_screens?catalogue_id=eq.{catalogue_id}"),
                        headers=h, timeout=8)
        if not slots:
            return True
        rows = [dict(s, catalogue_id=catalogue_id) for s in slots]
        h2 = dict(SB_HEADERS_ADMIN); h2["Prefer"] = "return=minimal"
        r = requests.post(_sb("/catalogue_screens"), headers=h2, json=rows, timeout=8)
        return r.status_code in (200, 201)
    except Exception as e:
        print("Catalogue screens replace error:", e)
    return False


# =====================================================================
# Schedule helpers (device timetable)
# =====================================================================
def get_device_schedule_bands(device_id):
    """Return ordered schedule bands with their catalogue + screens."""
    if not SB_REST:
        return []
    try:
        r = requests.get(
            _sb(f"/device_schedule?device_id=eq.{device_id}"
                f"&select=*,catalogue:catalogues!catalogue_id(*)"
                f"&order=sort_order.asc"),
            headers=SB_HEADERS_ADMIN, timeout=8)
        if r.status_code != 200:
            return []
        bands = r.json()
        for band in bands:
            cat = band.get("catalogue") or {}
            if cat.get("id"):
                cat["screens"] = get_catalogue_screens(cat["id"])
        return bands
    except Exception as e:
        print("Schedule get error:", e)
    return []


def save_device_schedule_bands(device_id, bands):
    if not SB_REST:
        return True
    try:
        h = dict(SB_HEADERS_ADMIN)
        requests.delete(_sb(f"/device_schedule?device_id=eq.{device_id}"),
                        headers=h, timeout=8)
        if not bands:
            return True
        rows = [dict(b, device_id=device_id) for b in bands]
        h2 = dict(SB_HEADERS_ADMIN); h2["Prefer"] = "return=minimal"
        r = requests.post(_sb("/device_schedule"), headers=h2, json=rows, timeout=8)
        return r.status_code in (200, 201)
    except Exception as e:
        print("Schedule save error:", e)
    return False


def get_active_schedule_band(device_id):
    """Return the band active at the current hour, or None."""
    try:
        bands = get_device_schedule_bands(device_id)
        if not bands:
            return None
        h = datetime.now(UK_TZ).hour
        start = 0
        for band in bands:
            end = band.get("end_hour", 0)
            end_eff = end if end > 0 else 24
            if start <= h < end_eff:
                return band
            start = end_eff
        return bands[-1]
    except Exception as e:
        print("Active schedule band error:", e)
        return None


def display_from_schedule_band(band, dev):
    """Build display response from an active schedule band."""
    catalogue = band.get("catalogue") or {}
    slots = catalogue.get("screens") or []
    brightness = band.get("brightness", 1.0)

    allowed_modes = []
    screen_durations = {}
    trains_boards = None
    has_weather = False

    for slot in slots:
        screen = slot.get("screen") or {}
        stype = screen.get("type", "")
        cfg = screen.get("config") or {}
        mode = TYPE_MODES.get(stype)
        if mode and mode not in allowed_modes:
            allowed_modes.append(mode)
            screen_durations[mode] = slot.get("duration_seconds", 10)
        if stype == "trains" and trains_boards is None:
            trains_boards = cfg.get("boards") or DEFAULT_BOARDS
        if stype == "weather":
            has_weather = True

    return {
        "brightness": brightness,
        "allowed_modes": allowed_modes,
        "screen_durations": screen_durations,
        "trains": get_trains(trains_boards) if trains_boards else [],
        "weather": get_weather() if has_weather else [],
        "message": current_message(dev),
        "epoch": int(time.time()),
        "tz_offset": uk_tz_offset_seconds(),
    }


# =====================================================================
# Trains
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
# Weather
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
                elif "snow" in cond:
                    d["icons"].append("snow")
                elif "thunder" in cond:
                    d["icons"].append("thunderstorm")
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
            else:
                wd = datetime.strptime(order[i], "%Y-%m-%d").weekday()
                label = ["MON","TUE","WED","THU","FRI","SAT","SUN"][wd]
            out.append({"day": label, "high": high, "low": low, "icon_name": mapped})
        _weather_cache["data"] = out
        _weather_cache["ts"] = now
        return out
    except Exception as e:
        print("OWM error", e)
        return _weather_cache["data"]


# =====================================================================
# Device polling endpoint
# =====================================================================
@app.get("/api/device/{device_id}/display")
def get_display(device_id: str, request: Request):
    incoming_secret = request.headers.get("x-device-secret", "")
    verify_device_secret(incoming_secret)
    dev = get_device(device_id)
    reboot = bool(dev.get("reboot"))
    fields = {"last_seen": int(time.time())}
    if reboot:
        fields["reboot"] = False
    save_device(device_id, fields)

    if not dev.get("paired", False):
        return {
            "paired": False, "pair_code": dev.get("pair_code", ""),
            "brightness": 0.5, "allowed_modes": ["PAIR"],
            "trains": [], "weather": [], "message": "",
            "reboot": reboot, "epoch": int(time.time()),
            "tz_offset": uk_tz_offset_seconds(),
        }

    band = get_active_schedule_band(device_id)
    if band:
        resp = display_from_schedule_band(band, dev)
        resp.update({"paired": True, "reboot": reboot})
        return resp

    # Legacy fallback
    bright, allowed = legacy_schedule_for(dev)
    boards = (dev.get("config") or {}).get("boards") or DEFAULT_BOARDS
    return {
        "paired": True, "brightness": bright, "allowed_modes": allowed,
        "trains": get_trains(boards), "weather": get_weather(),
        "message": current_message(dev),
        "reboot": reboot, "epoch": int(time.time()),
        "tz_offset": uk_tz_offset_seconds(),
    }


@app.get("/api/user/device/{device_id}/display")
def get_display_for_user(device_id: str, authorization: str = Header(default="")):
    user = verify_token(authorization)
    dev = get_device(device_id)
    if dev.get("owner_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not your device")
    if not dev.get("paired", False):
        return {"paired": False, "pair_code": dev.get("pair_code", "")}

    band = get_active_schedule_band(device_id)
    if band:
        resp = display_from_schedule_band(band, dev)
        resp["paired"] = True
        return resp

    bright, allowed = legacy_schedule_for(dev)
    boards = (dev.get("config") or {}).get("boards") or DEFAULT_BOARDS
    return {
        "paired": True, "brightness": bright, "allowed_modes": allowed,
        "trains": get_trains(boards), "weather": get_weather(),
        "message": current_message(dev),
    }


# =====================================================================
# User API
# =====================================================================
@app.get("/api/user/me")
def get_me(authorization: str = Header(default="")):
    user = verify_token(authorization)
    devices = get_user_devices(user["id"])
    return {
        "id": user["id"], "email": user.get("email"),
        "devices": [{"device_id": d["device_id"], "name": d.get("name", ""),
                     "last_seen": d.get("last_seen", 0)} for d in devices],
    }


class PairBody(BaseModel):
    code: str
    name: Optional[str] = None


@app.post("/api/user/pair")
def pair_device(body: PairBody, authorization: str = Header(default="")):
    user = verify_token(authorization)
    dev = find_device_by_code(body.code)
    if not dev:
        raise HTTPException(status_code=404, detail="Invalid or already-used code")
    save_device(dev["device_id"], {"paired": True, "owner_id": user["id"], "name": body.name or ""})
    return {"ok": True, "device_id": dev["device_id"], "name": body.name or ""}


class DeviceUpdate(BaseModel):
    message:  Optional[str]  = None
    reboot:   Optional[bool] = None
    name:     Optional[str]  = None


@app.post("/api/user/device/{device_id}")
def update_device(device_id: str, body: DeviceUpdate,
                  authorization: str = Header(default="")):
    user = verify_token(authorization)
    dev = get_device(device_id)
    if dev.get("owner_id") != user["id"]:
        raise HTTPException(status_code=403, detail="Not your device")
    fields = {}
    if body.message is not None:
        fields["message"] = body.message
        fields["message_ts"] = int(time.time())
    if body.reboot is not None:
        fields["reboot"] = body.reboot
    if body.name is not None:
        fields["name"] = body.name
    if fields:
        save_device(device_id, fields)
    return {"ok": True}


# =====================================================================
# Screens API
# =====================================================================
class ScreenCreate(BaseModel):
    name: str
    type: str
    config: dict = {}


class ScreenUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None


@app.get("/api/screens")
def list_screens(authorization: str = Header(default="")):
    user_id = None
    if authorization.startswith("Bearer "):
        try:
            user_id = verify_token(authorization)["id"]
        except HTTPException:
            pass
    return get_screens(user_id)


@app.post("/api/screens")
def create_screen_ep(body: ScreenCreate, authorization: str = Header(default="")):
    user = verify_token(authorization)
    if body.type not in VALID_TYPES:
        raise HTTPException(400, f"Invalid type. Must be one of: {', '.join(VALID_TYPES)}")
    item = create_screen(user["id"], body.dict())
    if not item:
        raise HTTPException(500, "Failed to create screen")
    return item


@app.patch("/api/screens/{screen_id}")
def update_screen_ep(screen_id: str, body: ScreenUpdate,
                     authorization: str = Header(default="")):
    user = verify_token(authorization)
    data = {k: v for k, v in body.dict().items() if v is not None}
    if not data:
        return {"ok": True}
    ok = update_screen(screen_id, user["id"], data)
    if not ok:
        raise HTTPException(404, "Not found or not your screen")
    return {"ok": True}


@app.delete("/api/screens/{screen_id}")
def delete_screen_ep(screen_id: str, authorization: str = Header(default="")):
    user = verify_token(authorization)
    ok = delete_screen(screen_id, user["id"])
    if not ok:
        raise HTTPException(404, "Not found or not your screen")
    return {"ok": True}


# =====================================================================
# Catalogues API
# =====================================================================
class CatalogueCreate(BaseModel):
    name: str


class CatalogueUpdate(BaseModel):
    name: Optional[str] = None


class CatalogueScreenSlot(BaseModel):
    screen_id: str
    duration_seconds: int = 10
    sort_order: int = 0


class CatalogueScreensReplace(BaseModel):
    slots: list[CatalogueScreenSlot]


@app.get("/api/catalogues")
def list_catalogues(authorization: str = Header(default="")):
    user_id = None
    if authorization.startswith("Bearer "):
        try:
            user_id = verify_token(authorization)["id"]
        except HTTPException:
            pass
    return get_catalogues(user_id)


@app.post("/api/catalogues")
def create_catalogue_ep(body: CatalogueCreate, authorization: str = Header(default="")):
    user = verify_token(authorization)
    cat = create_catalogue(user["id"], body.name)
    if not cat:
        raise HTTPException(500, "Failed to create catalogue")
    return cat


@app.patch("/api/catalogues/{catalogue_id}")
def update_catalogue_ep(catalogue_id: str, body: CatalogueUpdate,
                        authorization: str = Header(default="")):
    user = verify_token(authorization)
    data = {k: v for k, v in body.dict().items() if v is not None}
    if not data:
        return {"ok": True}
    ok = update_catalogue(catalogue_id, user["id"], data)
    if not ok:
        raise HTTPException(404, "Not found or not your catalogue")
    return {"ok": True}


@app.delete("/api/catalogues/{catalogue_id}")
def delete_catalogue_ep(catalogue_id: str, authorization: str = Header(default="")):
    user = verify_token(authorization)
    ok = delete_catalogue(catalogue_id, user["id"])
    if not ok:
        raise HTTPException(404, "Not found or not your catalogue")
    return {"ok": True}


@app.put("/api/catalogues/{catalogue_id}/screens")
def replace_catalogue_screens_ep(catalogue_id: str, body: CatalogueScreensReplace,
                                  authorization: str = Header(default="")):
    user = verify_token(authorization)
    ok = replace_catalogue_screens(catalogue_id, [s.dict() for s in body.slots])
    if not ok:
        raise HTTPException(500, "Failed to save catalogue screens")
    cat_screens = get_catalogue_screens(catalogue_id)
    return {"ok": True, "screens": cat_screens}


# =====================================================================
# Device schedule API
# =====================================================================
class ScheduleBand(BaseModel):
    catalogue_id: str
    end_hour: int
    brightness: float = 1.0
    sort_order: int = 0


class ScheduleReplace(BaseModel):
    bands: list[ScheduleBand]


@app.get("/api/user/device/{device_id}/schedule")
def get_schedule(device_id: str, authorization: str = Header(default="")):
    user = verify_token(authorization)
    dev = get_device(device_id)
    if dev.get("owner_id") != user["id"]:
        raise HTTPException(403, "Not your device")
    return get_device_schedule_bands(device_id)


@app.post("/api/user/device/{device_id}/schedule")
def replace_schedule(device_id: str, body: ScheduleReplace,
                     authorization: str = Header(default="")):
    user = verify_token(authorization)
    dev = get_device(device_id)
    if dev.get("owner_id") != user["id"]:
        raise HTTPException(403, "Not your device")
    ok = save_device_schedule_bands(device_id, [b.dict() for b in body.bands])
    if not ok:
        raise HTTPException(500, "Failed to save schedule")
    return {"ok": True}


# =====================================================================
# Station search
# =====================================================================
_stations = []


def _load_stations():
    global _stations
    if _stations:
        return
    try:
        r = requests.get(
            "https://raw.githubusercontent.com/davwheat/uk-railway-stations/main/stations.json",
            timeout=10)
        if r.status_code == 200:
            raw = r.json()
            _stations = sorted(
                [{"n": s["stationName"], "c": s["crsCode"]}
                 for s in raw if s.get("crsCode")],
                key=lambda x: x["n"])
            print(f"Loaded {len(_stations)} stations")
    except Exception as e:
        print("Station load error:", e)


@app.get("/api/stations")
def search_stations(q: str = ""):
    _load_stations()
    q = q.strip().lower()
    if not q or len(q) < 2:
        return []
    matches = [s for s in _stations if q in s["n"].lower()]
    prefix = [s for s in matches if s["n"].lower().startswith(q)]
    rest   = [s for s in matches if not s["n"].lower().startswith(q)]
    return (prefix + rest)[:10]


# =====================================================================
# Firmware + phone page
# =====================================================================
# In-memory OTA request log for debugging device update problems.
# Resets on each deploy; check via the "ota_requests" field on GET /.
_ota_log = {"version_checks": [], "app_downloads": []}


def _ota_note(kind):
    lst = _ota_log[kind]
    lst.append(datetime.now(UK_TZ).strftime("%Y-%m-%d %H:%M:%S"))
    if len(lst) > 10:
        lst.pop(0)


@app.get("/firmware/version")
def firmware_version():
    _ota_note("version_checks")
    return {"version": FIRMWARE_VERSION}


@app.get("/firmware/app")
def firmware_app():
    _ota_note("app_downloads")
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, "device_app.py")) as f:
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
    return {
        "status": "ok",
        "firmware_version": FIRMWARE_VERSION,
        "rdm_key_set": bool(RDM_API_KEY),
        "owm_key_set": bool(OWM_API_KEY),
        "persistence": "supabase" if SB_REST else "in-memory",
        "device_secret_set": bool(DEVICE_SECRET),
        "ota_requests": _ota_log,
    }
