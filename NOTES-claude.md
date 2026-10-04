# NOTES-claude.md — VOXEL

Running log for Claude Code sessions. Newest entry at the bottom.

## 2026-08-19 — Inventory + secret scan (pre-GitHub audit)

- Git repo, 76 commits, remote **public**: github.com/JakeOOS/led-screen-server. Dirty tree: 13 modified + 6 untracked (WeatherAnimations/, Play listing, etc). No README/CLAUDE.md.
- gitleaks git history: only hits are the **Supabase anon JWT** in `control.html` (4 commits since 2026-06-20, still in HEAD + app/www/index.html). Anon keys are public-by-design *if* Supabase RLS is enforced — verify RLS; otherwise rotate in Supabase dashboard.
- Previously-leaked WiFi password + DEVICE_SECRET: confirmed purged from all history on origin/main (placeholders only). Rotation steps in CREDENTIAL-ROTATION.md still need doing by Jack if not done.
- `backups/device_main_as_flashed_2026-07-08.py:31` still holds the WiFi password — gitignored, untracked → safe locally, but rotate per the doc.
- `app/android/voxel-upload.jks` is ignored via app/.gitignore (*.jks). `server.py` reads all keys from env. Good.
- Readiness: **Already on GitHub (public)**. Decide: keep public, or flip to private for remote sessions. Commit/park the dirty work first.

**Left off:** awaiting Jack's go-ahead on remediation / push. Nothing pushed, no history rewritten.

## 2026-09-11 — Hardware check (Cowork)

- Jack asked what hardware VOXEL uses (context: comparing to a Reddit post about a Claude-designed RP2350 + e-ink PCB).
- From `device_app.py`: **Pimoroni Interstate 75 W** (Wi-Fi HUB75 driver board, MicroPython, `interstate75` + `network` modules) driving a **64×32 RGB LED matrix (HUB75)**, panel type **FM6126A** (falls back to default driver if unsupported).
- Code doesn't pin down which chip variant of the I75 W (RP2040 Pico W vs newer RP2350). No buttons/sensors used in firmware.
- No changes made to code.

## 2026-10-04 — Standalone rewrite (branch `standalone`, nothing committed or pushed)

- Jack's call: not releasing to anyone else, so drop the server, accounts, pairing and the Android app. Keep trains, weather, the laptop-made animation and Claude news. Live design preview and the phone message screen are dropped.
- `device_app.py` (fw 33) now fetches trains (RDM) and weather (OWM) itself, streaming the JSON one array element at a time to stay inside RAM. Clock is NTP + on-device UK DST. Schedule, boards, brightness and `anim_url` come from `config.json` in the repo (cached on flash).
- News: `.github/workflows/news.yml` runs `tools/news.py` hourly and force-pushes `news.json` to the `data` branch. Needs repo secret `ANTHROPIC_API_KEY`.
- OTA: `ota_bootloader.py` reads `"firmware"` from `config.json` and pulls `device_app.py` from raw GitHub. To ship: bump `FW_VERSION` in device_app.py and `"firmware"` in config.json together. Bad versions are rolled back and remembered in `bad_version.txt`. Bootloader now imports `app` rather than exec-ing its source (saves ~50KB RAM).
- `device_config.py` on the device now needs: WIFI_SSID, WIFI_PASSWORD, OWM_API_KEY, RDM_API_KEY.
- Flashed to the screen over USB the same day (old files backed up in `backups/device_2026-10-04/`). Board is an **Interstate 75 W RP2350**, MicroPython 1.25 preview, ~440KB free RAM, so memory is not a concern. Boot, wifi, NTP, HTTPS and the animation download all work on hardware. Trains/weather return 401 until the API keys are added to `device_config.py`; the streaming parser is still unproven against real API data.
- Device flash is 2MB and `/lib/pygame` (1.6MB, an accidental desktop install) fills most of it: ~53KB free. OTA needs ~55KB spare per update, so pygame should be removed from the device (awaiting Jack's OK).
- `config.json` schedule was seeded from the old DEFAULT_SCHEDULE, not from the live Supabase schedule.
- Old server files (`server.py`, `control.html`, `app/`, privacy pages, `tools/preview_watcher.py`) are untouched; remove once the screen is confirmed working, then retire Render + Supabase.

**Left off:** awaiting Jack: OWM + RDM keys into `device_config.py` (local, then copy to device), OK to delete `/lib/pygame` from the device, push to main, add the Actions secret.
