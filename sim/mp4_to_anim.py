"""Convert an MP4 (e.g. an After Effects render) into the anim.bin format
device_app.py's ANIM mode plays: a fixed palette + one byte per pixel per frame.

Usage:
    python3 sim/mp4_to_anim.py design.mp4                    # writes ./anim.bin
    python3 sim/mp4_to_anim.py design.mp4 -o anim.bin --colors 64 --fit contain

Then in the simulator: press 'r' to pick up the new anim.bin, and '5' for ANIM mode.
Playback on the real device is fixed at 10fps (it shows each frame for 100ms), so
frames are resampled to that rate regardless of the source video's frame rate.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

DEVICE_FPS = 10   # matches (now_ticks // 100) % nframes in device_app.py's draw_animation
W, H = 64, 32


def extract_frames(input_path, tmpdir, fps, fit, nearest):
    interp = "neighbor" if nearest else "lanczos"
    if fit == "cover":
        vf = f"fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase:flags={interp},crop={W}:{H}"
    else:  # contain
        vf = (f"fps={fps},scale={W}:{H}:force_original_aspect_ratio=decrease:flags={interp},"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black")

    out_pattern = os.path.join(tmpdir, "f_%05d.png")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-vf", vf, out_pattern],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr[-2000:], file=sys.stderr)
        raise SystemExit("ffmpeg failed -- see output above")

    files = sorted(f for f in os.listdir(tmpdir) if f.endswith(".png"))
    if not files:
        raise SystemExit("ffmpeg produced no frames")
    return [Image.open(os.path.join(tmpdir, f)).convert("RGB") for f in files]


def build_anim_bytes(frames, colors, dither):
    n = len(frames)
    strip = Image.new("RGB", (W, H * n))
    for i, frame in enumerate(frames):
        strip.paste(frame, (0, H * i))

    dither_mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    quant = strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=dither_mode)

    palette = quant.getpalette()[: colors * 3]
    palette += [0] * (colors * 3 - len(palette))  # pad if fewer distinct colors were used
    indices = quant.tobytes()

    header = b"LDA1" + bytes([W, H]) + colors.to_bytes(2, "little") + n.to_bytes(2, "little")
    return header + bytes(palette) + indices


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="source MP4 (or any file ffmpeg can read)")
    ap.add_argument("-o", "--output", default="anim.bin", help="output path (default: ./anim.bin)")
    ap.add_argument("--fps", type=int, default=DEVICE_FPS, help="frames/sec to sample (default: 10, matches device playback)")
    ap.add_argument("--colors", type=int, default=48, help="palette size, 2-256 (default: 48)")
    ap.add_argument("--fit", choices=["cover", "contain"], default="cover", help="cover=crop to fill, contain=letterbox")
    ap.add_argument("--nearest", action="store_true", help="use nearest-neighbour scaling for a blocky/pixel-art look")
    ap.add_argument("--dither", action="store_true", help="dither the palette quantization (default: off, crisper on a small grid)")
    args = ap.parse_args()

    if not (2 <= args.colors <= 256):
        raise SystemExit("--colors must be between 2 and 256")

    tmpdir = tempfile.mkdtemp(prefix="voxel_anim_")
    try:
        frames = extract_frames(args.input, tmpdir, args.fps, args.fit, args.nearest)
        data = build_anim_bytes(frames, args.colors, args.dither)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    with open(args.output, "wb") as f:
        f.write(data)

    print(f"Wrote {args.output}: {len(frames)} frames, {args.colors} colors, {len(data)/1024:.1f} KB")


if __name__ == "__main__":
    main()
