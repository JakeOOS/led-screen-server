"""Build the split weather-screen animations for the VOXEL LED screen.

Scans a folder for After Effects exports. Naming: the condition name
(sunny/cloudy/rain/stormy/snow) anywhere in the filename; files with
"mini" in the name are the right-hand 12x32 strip, everything else is
the 52x32 left side. So these all work:

    WeatherIdea_02 {Sunny}_1.mov          -> sunny left  (52x32)
    WeatherIdea_02 {Sunny} {Mini}.mov     -> sunny right (12x32)

Exact multiples (520x320 / 120x320) are fine too. Snow is optional —
the server falls back to rain until it exists. Converts each to the
LDA1 anim format at 10fps and writes weather_anims/<cond>_<L|R>.bin in
the repo. Commit + push those and Render serves them to the screen.

Usage:
    python3 tools/build_weather_anims.py        # reads ~/Desktop/WeatherAnimations
    python3 tools/build_weather_anims.py --src ~/some/folder
"""

import argparse
import os
import re
import sys
import tempfile
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "sim"))
from mp4_to_anim import extract_frames, build_anim_bytes  # noqa: E402

CONDITIONS = ["sunny", "cloudy", "rain", "stormy", "snow"]
SIZES = {"L": (52, 32), "R": (12, 32)}
EXTS = (".mp4", ".mov", ".gif", ".webm")
OUT_DIR = os.path.join(REPO, "weather_anims")


def video_size(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=20).stdout.strip()
    w, h = map(int, out.split(",")[:2])
    return w, h


def find_source(folder, cond, side):
    """Newest file for this condition+side. Side R = 'mini' in the name,
    side L = the condition without 'mini'."""
    best = None
    for name in os.listdir(folder):
        stem, ext = os.path.splitext(name)
        low = stem.lower()
        if ext.lower() not in EXTS or cond not in low:
            continue
        is_mini = "mini" in low
        if (side == "R") != is_mini:
            continue
        p = os.path.join(folder, name)
        m = os.stat(p).st_mtime
        if best is None or m > best[1]:
            best = (p, m)
    return best[0] if best else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=os.path.expanduser("~/Desktop/WeatherAnimations"))
    ap.add_argument("--colors", type=int, default=256)
    args = ap.parse_args()

    if not os.path.isdir(args.src):
        raise SystemExit(f"Source folder not found: {args.src}")
    os.makedirs(OUT_DIR, exist_ok=True)

    built, missing = [], []
    for cond in CONDITIONS:
        for side, (w, h) in SIZES.items():
            src = find_source(args.src, cond, side)
            if not src:
                missing.append(f"{cond}_{side}")
                continue
            sw, sh = video_size(src)
            mult_w, mult_h = sw / w, sh / h
            if mult_w != mult_h or sw % w or sh % h:
                print(f"  ⚠ {os.path.basename(src)} is {sw}x{sh} — expected {w}x{h} "
                      f"or an exact multiple. Skipping.")
                missing.append(f"{cond}_{side}")
                continue
            nearest = sw > w   # exact multiple: crisp downscale
            tmpdir = tempfile.mkdtemp(prefix="voxel_weather_")
            try:
                frames = extract_frames(src, tmpdir, fps=10, fit="cover",
                                        nearest=nearest, w=w, h=h)
                data = build_anim_bytes(frames, args.colors, dither=False, w=w, h=h)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)
            out = os.path.join(OUT_DIR, f"{cond}_{side}.bin")
            with open(out, "wb") as f:
                f.write(data)
            built.append(f"{cond}_{side}.bin ({len(frames)} frames, {len(data)/1024:.1f} KB)")
            print(f"  ✓ {os.path.basename(src)} -> {cond}_{side}.bin "
                  f"({len(frames)} frames, {len(data)/1024:.1f} KB)")

    print(f"\nBuilt {len(built)} file(s) into {OUT_DIR}")
    if missing:
        print("Not found (fine if intentional):", ", ".join(missing))
    if built:
        print("\nNow commit & push so the screen can fetch them:")
        print("  git add weather_anims && git commit -m 'Update weather animations' && git push")


if __name__ == "__main__":
    main()
