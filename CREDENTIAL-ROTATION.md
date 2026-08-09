# Credential rotation — required

The repository is public. Until 9 August 2026 it contained, in `device_app.py`:

- the home WiFi SSID and its password
- `DEVICE_SECRET`, the shared secret the screen uses to authenticate to the
  server

`server.py` also served that file from `/firmware/app` with no authentication,
so the same values were readable straight off the live deployment without
touching GitHub.

Both problems are fixed in the code: credentials now live in `device_config.py`
(gitignored), `/firmware/app` requires the device secret, and the values have
been purged from all 75 commits of git history.

**None of that helps while the old credentials still work.** They were public
for roughly a month, on an indexable repo. Assume they were scraped. The
following are the steps that actually close the exposure, and they need you.

## 1. Change the WiFi password

On the router (Sky). Changing the password is the important part; the SSID is
only a locator. Every device on the network needs the new password, including
the screen — see step 3.

Consider changing the SSID too. It was a router default and, paired with the
device name that was in the same file, narrows the location enough to be worth
breaking the link. (Neither value is repeated in this file — writing them down
in a public repo is what caused the problem.)

## 2. Rotate `DEVICE_SECRET`

Generate a new one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set it in the Render environment as `DEVICE_SECRET`, and redeploy.

## 3. Reflash the device

Create `device_config.py` from `device_config.example.py`, filling in the new
WiFi password and the new device secret:

```python
DEVICE_SECRET = "<the new secret from step 2>"
WIFI_SSID = "<your SSID>"
WIFI_PASSWORD = "<the new password from step 1>"
SERVER_URL = "https://led-screen-server.onrender.com"
DEVICE_ID = "screen-01"
```

Copy it to the device alongside `app.py` and `main.py`. The device will not boot
without it — that is deliberate, so a unit can never fall back to running with
blank credentials.

Do this in the same sitting as step 2. Between rotating the server secret and
reflashing, the screen cannot authenticate and will show failures.

## 4. Rotate the other API keys

They were never committed — they come from the Render environment — but they sat
behind a server whose device secret was public. Cheap insurance, and worth doing
while you are in there: `OWM_API_KEY`, `RDM_API_KEY`, `ANTHROPIC_API_KEY`.

`SUPABASE_KEY` is the service_role key. Rotating it means reissuing from the
Supabase dashboard and updating Render.

## 5. Force-push the rewritten history

History has been rewritten locally but **not pushed** — the public repo still
carries the credentials in its old commits. See the "Publishing the rewrite"
section below.

Note that force-pushing does not fully erase them. GitHub keeps unreachable
commits accessible by SHA until garbage collection, forks keep their own copies,
and anything already cached or scraped stays out there. This is why steps 1–4
are the ones that matter; the rewrite is tidying up after the fact.

If you want the old objects actually gone rather than just unreferenced, open a
GitHub support request to garbage-collect the repository after force-pushing.

## Publishing the rewrite

Every commit SHA changed, so this is a force-push and it rewrites the public
branch:

```bash
git push --force-with-lease origin main
```

Anyone else with a clone will need to re-clone or reset; if it is only you, that
does not matter.

A verified backup of the original history is in the session scratchpad as
`voxel-full-backup.bundle`, restorable with `git clone voxel-full-backup.bundle`.
Copy it somewhere durable before you force-push if you want to keep it — the
scratchpad is temporary.

## Preventing a repeat

`.gitignore` now covers `device_config.py`, `ota_bootloader.py`, `backups/`, and
the app's signing material. Anything holding a credential belongs in
`device_config.py` or the Render environment, never in a tracked file.
