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
