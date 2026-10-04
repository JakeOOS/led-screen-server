# =====================================================================
#  OTA BOOTLOADER  --  flash this to the device ONCE as main.py
# =====================================================================
#  On every boot this does:
#    1. connect wifi
#    2. read config.json on GitHub for the firmware version to run
#    3. if newer, download app.py, CHECK IT COMPILES, then swap it in
#       (keeping the previous version as a backup)
#    4. run app.py
#    5. if app.py crashes within STABILITY_SECONDS, assume the new code
#       is broken and ROLL BACK to the backup automatically
#
#  You should rarely need to change this file again. To change what the
#  screen DOES, edit device_app.py in the GitHub repo, set FW_VERSION in it
#  and "firmware" in config.json to the same new number, and push.
# =====================================================================

import time
import network
import urequests
import os
import gc
import machine
import json

# --- CONFIG (this is the only thing baked into the device) ---
# Credentials come from device_config.py, which is gitignored and flashed to the
# device separately. Copy device_config.example.py and fill it in.
from device_config import WIFI_SSID, WIFI_PASSWORD

REPO_RAW = "https://raw.githubusercontent.com/JakeOOS/led-screen-server/main"
VERSION_URL = REPO_RAW + "/config.json"
APP_URL = REPO_RAW + "/device_app.py"

APP_FILE = "app.py"
BACKUP_FILE = "app_backup.py"
NEW_FILE = "app_new.py"
VERSION_FILE = "version.txt"
BAD_VERSION_FILE = "bad_version.txt"    # a version that crashed and was rolled back

STABILITY_SECONDS = 30      # crash faster than this => treat new code as bad, roll back
WIFI_TIMEOUT = 40           # was 15s -- too short for a cold boot to associate, causing
                            # device_app.py to start offline and show WIFI/WEATHER/TRAINS FAIL


def log(*a):
    print("[OTA]", *a)


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    time.sleep(0.5)              # settle after reset
    try:
        wlan.active(True)
    except OSError:
        return False
    time.sleep(1)                # CRITICAL: let the CYW43 radio initialise
    for _attempt in range(2):    # two full attempts before giving up
        if wlan.isconnected():
            break
        try:
            wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        except OSError:
            time.sleep(2)
            continue
        t = WIFI_TIMEOUT
        while t > 0 and not wlan.isconnected():
            time.sleep(1)
            t -= 1
    if wlan.isconnected():
        log("wifi connected:", wlan.ifconfig()[0])
        return True
    return False


def file_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def write_text(path, v):
    try:
        with open(path, "w") as f:
            f.write(v)
    except OSError:
        pass


def read_local_version():
    return read_text(VERSION_FILE)


def write_local_version(v):
    write_text(VERSION_FILE, v)


def get_remote_version():
    # Retry: the first request right after wifi connect often hits an
    # unsettled network stack.
    for attempt in range(3):
        try:
            gc.collect()
            r = urequests.get(VERSION_URL + "?t=" + str(time.ticks_ms()), timeout=15)
            v = str(r.json().get("firmware", "")) if r.status_code == 200 else ""
            r.close()
            if v:
                return v
        except Exception as e:
            log("version check failed (try %d):" % (attempt + 1), e)
        time.sleep(2)
    return ""


def download_app():
    """Download candidate to NEW_FILE. Returns bytes written, or -1 on failure."""
    try:
        gc.collect()
        r = urequests.get(APP_URL + "?t=" + str(time.ticks_ms()), timeout=20)
        if r.status_code != 200:
            log("app download status", r.status_code)
            r.close()
            return -1
        expected = None
        try:
            cl = r.headers.get("Content-Length")
            if cl:
                expected = int(cl)
        except Exception:
            expected = None
        written = 0
        with open(NEW_FILE, "wb") as f:
            while True:
                chunk = r.raw.read(512)
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
        r.close()
        if expected is not None and written != expected:
            log("size mismatch:", written, "expected", expected)
            return -1
        return written
    except Exception as e:
        log("download failed:", e)
        try:
            os.remove(NEW_FILE)
        except OSError:
            pass
        return -1


def validate(path, version):
    """Sanity check: file is non-trivial, IS the version we asked for, and
    compiles without syntax errors. GitHub caches raw files for a few minutes,
    so right after a push config.json can name a version while device_app.py
    is still the old one — that download is discarded and retried later."""
    try:
        with open(path) as f:
            src = f.read()
        if len(src) < 50:
            log("candidate too small")
            return False
        if ('FW_VERSION = "%s"' % version) not in src:
            log("candidate is not version", version, "(GitHub cache?)")
            return False
        compile(src, path, "exec")     # raises if the Python is broken
        return True
    except Exception as e:
        log("validation failed:", e)
        return False


def install_update():
    remote = get_remote_version()
    local = read_local_version()
    if not remote:
        log("no remote version available; skipping update")
        return
    if remote == local and file_exists(APP_FILE):
        log("already up to date:", local)
        return
    if remote == read_text(BAD_VERSION_FILE) and file_exists(APP_FILE):
        log("version", remote, "crashed before; waiting for a newer one")
        return
    log("update available:", repr(local), "->", repr(remote))

    if download_app() <= 0:
        log("download failed; keeping current app")
        return
    if not validate(NEW_FILE, remote):
        log("candidate failed validation; discarding")
        try:
            os.remove(NEW_FILE)
        except OSError:
            pass
        return

    # Preserve the current working app as a backup before replacing it.
    if file_exists(APP_FILE):
        try:
            if file_exists(BACKUP_FILE):
                os.remove(BACKUP_FILE)
            os.rename(APP_FILE, BACKUP_FILE)
        except OSError as e:
            log("backup step failed:", e)
    try:
        os.rename(NEW_FILE, APP_FILE)
        write_local_version(remote)
        log("installed version", remote)
    except OSError as e:
        log("install failed:", e)


def rollback():
    if not file_exists(BACKUP_FILE):
        log("no backup to roll back to")
        return
    log("rolling back to previous working version")
    write_text(BAD_VERSION_FILE, read_local_version())
    try:
        if file_exists(APP_FILE):
            os.remove(APP_FILE)
        os.rename(BACKUP_FILE, APP_FILE)
        write_local_version("rolledback")
    except OSError as e:
        log("rollback failed:", e)


def run_app():
    if not file_exists(APP_FILE):
        log("no app.py present -- nothing to run")
        return
    start = time.time()
    try:
        gc.collect()
        # Import rather than read-and-exec: the import compiles straight from
        # flash, so no copy of the source (50KB+) sits in RAM while it runs.
        import app
        app.main()
        log("app exited on its own; rebooting")
    except Exception as e:
        elapsed = time.time() - start
        log("app crashed after %ds:" % elapsed, e)
        if elapsed < STABILITY_SECONDS:
            log("fast crash -> new code looks broken")
            rollback()
        else:
            log("late crash -> probably transient; keeping current code")


# =====================================================================
#  BOOT SEQUENCE
# =====================================================================
log("bootloader starting")
if connect_wifi():
    try:
        install_update()
    except Exception as e:
        log("update step errored (continuing to run app):", e)
else:
    log("no wifi -- running whatever app is already installed, offline")

run_app()

# Whatever happened, reboot so we cleanly re-enter the bootloader.
log("rebooting in 3s")
time.sleep(3)
machine.reset()
