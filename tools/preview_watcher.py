"""Live design previewer for the VOXEL LED screen.

Watches a folder for design files. When you save an MP4/MOV/GIF or PNG/JPG
into it, the newest file is converted to the screen's anim.bin format and
uploaded to the server — the screen switches to showing it within ~20s
(one poll cycle). Delete everything from the folder to give the screen
back to its normal schedule.

Usage:
    python3 tools/preview_watcher.py                       # watches ~/Desktop/LED_PREVIEW
    python3 tools/preview_watcher.py --folder ~/designs
    python3 tools/preview_watcher.py --secret <device-secret>

The device secret defaults to the one baked into device_app.py so no
setup is needed on this machine.

Requires: Pillow (pip install Pillow); ffmpeg on PATH for video files.
"""

import argparse
import os
import sys
import tempfile
import shutil
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
from mp4_to_anim import extract_frames, build_anim_bytes, W, H  # noqa: E402

from PIL import Image  # noqa: E402

SERVER_URL = "https://led-screen-server.onrender.com"
DEFAULT_FOLDER = os.path.expanduser("~/Desktop/LED_PREVIEW")
VIDEO_EXT = {".mp4", ".mov", ".gif", ".webm", ".avi"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp"}
POLL_SECONDS = 2


def is_exact_multiple(w, h):
    """True when the source is a clean multiple of 64x32 (e.g. a 640x320
    After Effects comp) — then nearest-neighbour downscaling keeps pixel
    art crisp instead of smoothing it."""
    return w % W == 0 and h % H == 0 and w // W == h // H


def video_size(path):
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=20).stdout.strip()
        w, h = map(int, out.split(",")[:2])
        return w, h
    except Exception:
        return None


def image_to_frame(path, fit="cover"):
    """Load a still image and scale it to 64x32 the same way ffmpeg does."""
    img = Image.open(path).convert("RGB")
    src_w, src_h = img.size
    resample = Image.NEAREST if is_exact_multiple(src_w, src_h) else Image.LANCZOS
    scale = (max if fit == "cover" else min)(W / src_w, H / src_h)
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    img = img.resize((new_w, new_h), resample)
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    canvas.paste(img, ((W - new_w) // 2, (H - new_h) // 2))
    return canvas


def convert(path, colors, fit):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMAGE_EXT:
        return build_anim_bytes([image_to_frame(path, fit)], colors, dither=False)
    size = video_size(path)
    nearest = bool(size and is_exact_multiple(*size))
    if nearest:
        print(f"  {size[0]}x{size[1]} is an exact multiple of 64x32 -> crisp nearest-neighbour scaling")
    tmpdir = tempfile.mkdtemp(prefix="voxel_preview_")
    try:
        frames = extract_frames(path, tmpdir, fps=10, fit=fit, nearest=nearest)
        return build_anim_bytes(frames, colors, dither=False)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def http(method, url, data=None, secret=""):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"x-device-secret": secret,
                                          "Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def newest_design(folder):
    """Return (path, mtime) of the newest design file in the folder, or None."""
    best = None
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    for name in names:
        if name.startswith("."):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in VIDEO_EXT | IMAGE_EXT:
            continue
        p = os.path.join(folder, name)
        try:
            m = os.stat(p).st_mtime
        except OSError:
            continue
        if best is None or m > best[1]:
            best = (p, m)
    return best


def file_settled(path):
    """True once the file size stops changing (export/copy finished)."""
    try:
        s1 = os.path.getsize(path)
        time.sleep(0.6)
        return os.path.getsize(path) == s1 and s1 > 0
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", default=DEFAULT_FOLDER)
    ap.add_argument("--secret", default="tulsehill-screen-2026-x7k2m9")
    # 256 = the format's max; smooth gradients (clouds, glows) hog palette
    # slots, and at lower counts rare colours (a lightning flash) get merged
    # into their nearest neighbour.
    ap.add_argument("--colors", type=int, default=256)
    ap.add_argument("--fit", choices=["cover", "contain"], default="cover")
    args = ap.parse_args()

    os.makedirs(args.folder, exist_ok=True)
    print(f"Watching {args.folder}")
    print("Drop an MP4/MOV/GIF/PNG/JPG in there and the screen will show it ~20s later.")
    print("Empty the folder to give the screen back to its normal schedule.\n")

    last_uploaded = None       # (path, mtime) of what's currently on screen
    preview_active = False

    while True:
        try:
            best = newest_design(args.folder)

            if best is None and preview_active:
                print("Folder empty -> restoring normal screen schedule...")
                http("DELETE", SERVER_URL + "/api/preview/anim", secret=args.secret)
                preview_active = False
                last_uploaded = None
                print("Done. Screen returns to normal within ~20s.\n")

            elif best is not None and best != last_uploaded:
                path = best[0]
                if not file_settled(path):
                    time.sleep(POLL_SECONDS)
                    continue
                name = os.path.basename(path)
                print(f"Converting {name} ...")
                try:
                    data = convert(path, args.colors, args.fit)
                except SystemExit as e:
                    print(f"  conversion failed: {e}\n")
                    last_uploaded = best   # don't retry a broken file forever
                    time.sleep(POLL_SECONDS)
                    continue
                print(f"  {len(data)/1024:.1f} KB -> uploading...")
                http("POST", SERVER_URL + "/api/preview/anim", data=data, secret=args.secret)
                print(f"  Uploaded. The screen will show '{name}' within ~20s.\n")
                last_uploaded = best
                preview_active = True

        except urllib.error.URLError as e:
            print(f"  network error: {e} (will retry)\n")
        except KeyboardInterrupt:
            if preview_active:
                print("\nStopping — restoring normal screen schedule...")
                try:
                    http("DELETE", SERVER_URL + "/api/preview/anim", secret=args.secret)
                except Exception:
                    print("(couldn't reach server — run again and Ctrl-C, or the screen "
                          "stays in preview until cleared)")
            raise SystemExit(0)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
