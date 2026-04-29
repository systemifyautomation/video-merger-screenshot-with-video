#!/usr/bin/env python3
"""
Loom-style Video Creator
========================
Creates a 1080p video with a screenshot as the background and a webcam/face-cam
video in a circular frame at the bottom-right corner — just like Loom.

Usage
-----
    python merger.py screenshot.png webcam.mp4 output.mp4

    # Custom circle size and margin
    python merger.py screenshot.png webcam.mp4 output.mp4 \\
        --circle-size 320 --margin 40 --border-color "#FFFFFF"

    # With shadow effect
    python merger.py screenshot.png webcam.mp4 output.mp4 --shadow

Requirements
------------
    pip install -r requirements.txt
    # + ffmpeg must be installed on the system
"""

import argparse
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _probe_duration(path: str) -> float:
    """Return the duration (seconds) of a media file via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed for '{path}':\n{result.stderr.strip()}"
        )
    return float(result.stdout.strip())


def _hex_to_ffmpeg_color(color: str) -> str:
    """Convert a CSS hex color (#RRGGBB) to FFmpeg color notation (0xRRGGBB)."""
    color = color.strip()
    if color.startswith("#"):
        return "0x" + color[1:]
    return color  # already a named color like 'white'


# ---------------------------------------------------------------------------
# Core compositor
# ---------------------------------------------------------------------------

def create_loom_video(
    screenshot_path: str,
    webcam_path: str,
    output_path: str,
    *,
    circle_size: int = 280,
    margin: int = 30,
    border_width: int = 5,
    border_color: str = "white",
    shadow: bool = True,
    fps: int = 30,
    duration: float | None = None,
    hw_accel: bool = False,
    preset: str = "fast",
    crf: int = 23,
) -> None:
    """
    Create a Loom-style 1080p video.

    Parameters
    ----------
    screenshot_path : str
        Path to the background screenshot (PNG / JPG / …).
    webcam_path : str
        Path to the webcam / face-cam video (MP4 / MOV / …).
    output_path : str
        Destination MP4 path.
    circle_size : int
        Diameter in pixels of the circular webcam overlay (default 280).
    margin : int
        Distance from the right and bottom edges in pixels (default 30).
    border_width : int
        Width of the solid border ring around the circle (default 5).
    border_color : str
        Border colour — CSS hex (#RRGGBB) or FFmpeg named colour (default "white").
    shadow : bool
        Draw a soft drop-shadow behind the circle (default True).
    fps : int
        Output frame rate (default 30).
    duration : float | None
        Override duration in seconds.  None → use webcam video duration.
    hw_accel : bool
        Attempt to use NVENC hardware encoder (falls back to libx264 on failure).
    preset : str
        libx264 / NVENC preset (default "fast").
    crf : int
        Quality factor for libx264 (lower = better quality, default 23).
    """

    # ---- validate inputs ---------------------------------------------------
    for p in (screenshot_path, webcam_path):
        if not Path(p).exists():
            raise FileNotFoundError(f"Input file not found: {p}")

    # ---- duration ----------------------------------------------------------
    if duration is None:
        duration = _probe_duration(webcam_path)
        print(f"  Webcam duration : {duration:.2f} s")

    # ---- derived geometry --------------------------------------------------
    border_total  = circle_size + border_width * 2
    shadow_offset = border_width + 6          # shadow slightly larger than border
    shadow_total  = circle_size + shadow_offset * 2

    # Overlay positions (FFmpeg overlay expressions use the overlay stream's
    # width/height as `w` and `h`, and main stream as `W` and `H`).
    x_webcam = 1920 - circle_size  - margin
    y_webcam = 1080 - circle_size  - margin
    x_border = x_webcam - border_width
    y_border = y_webcam - border_width
    x_shadow = x_webcam - shadow_offset
    y_shadow = y_webcam - shadow_offset

    ff_border_color = _hex_to_ffmpeg_color(border_color)

    # ---- build filter_complex ----------------------------------------------
    # Label plan:
    #   [bg]           – 1920×1080 screenshot
    #   [webcam_raw]   – webcam scaled to circle_size × circle_size
    #   [webcam_circ]  – webcam with alpha circular mask
    #   [border_circ]  – solid-colour circle (border ring)
    #   [shadow_circ]  – semi-transparent dark circle (drop-shadow)
    #   [v0]           – bg + shadow (optional)
    #   [v1]           – v0 + border
    #   [out]          – v1 + webcam

    parts: list[str] = []

    # 1. Scale screenshot to exactly 1920×1080 (letterbox / pad as needed)
    parts.append(
        "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black[bg]"
    )

    # 2. Scale webcam and apply circular alpha mask
    r = circle_size / 2
    parts.append(
        f"[1:v]scale={circle_size}:{circle_size},"
        f"format=yuva420p,"
        f"geq="
        f"r='r(X,Y)':"
        f"g='g(X,Y)':"
        f"b='b(X,Y)':"
        f"a='if(lte(pow(X-{r},2)+pow(Y-{r},2),pow({r},2)),255,0)'"
        f"[webcam_circ]"
    )

    # 3. Border circle
    br = border_total / 2
    parts.append(
        f"color={ff_border_color}:s={border_total}x{border_total}:d={duration},"
        f"format=yuva420p,"
        f"geq="
        f"r='r(X,Y)':"
        f"g='g(X,Y)':"
        f"b='b(X,Y)':"
        f"a='if(lte(pow(X-{br},2)+pow(Y-{br},2),pow({br},2)),255,0)'"
        f"[border_circ]"
    )

    # 4. Optional shadow circle (semi-transparent dark disc)
    if shadow:
        sr = shadow_total / 2
        parts.append(
            f"color=0x000000:s={shadow_total}x{shadow_total}:d={duration},"
            f"format=yuva420p,"
            f"geq="
            f"r='0':"
            f"g='0':"
            f"b='0':"
            f"a='if(lte(pow(X-{sr},2)+pow(Y-{sr},2),pow({sr},2)),140,0)'"
            f"[shadow_circ]"
        )
        # Composite: bg → shadow → border → webcam
        parts.append(f"[bg][shadow_circ]overlay={x_shadow}:{y_shadow}[v_shadow]")
        parts.append(f"[v_shadow][border_circ]overlay={x_border}:{y_border}[v_border]")
    else:
        # Composite: bg → border → webcam
        parts.append(f"[bg][border_circ]overlay={x_border}:{y_border}[v_border]")

    parts.append(f"[v_border][webcam_circ]overlay={x_webcam}:{y_webcam}[out]")

    filter_complex = ";".join(parts)

    # ---- build ffmpeg command ----------------------------------------------
    def _build_cmd(use_nvenc: bool) -> list[str]:
        """Return the FFmpeg command list for the given encoder choice."""
        c = [
            "ffmpeg", "-y",
            # Loop the screenshot for the full duration
            "-loop", "1", "-framerate", str(fps), "-i", screenshot_path,
            # Webcam video
            "-i", webcam_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "1:a?",           # include audio from webcam if present
            # Encoding
            "-c:v", "h264_nvenc" if use_nvenc else "libx264",
            "-preset", preset,
        ]
        if not use_nvenc:
            c += ["-crf", str(crf)]
        c += [
            "-c:a", "aac",
            "-b:a", "128k",
            "-t", str(duration),
            "-r", str(fps),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",  # web-optimised: moov atom at front
            output_path,
        ]
        return c

    # ---- run ---------------------------------------------------------------
    print(f"\n▶  Creating Loom-style video ...")
    print(f"   Screenshot  : {screenshot_path}")
    print(f"   Webcam      : {webcam_path}")
    print(f"   Output      : {output_path}")
    print(f"   Circle size : {circle_size}px  |  Margin: {margin}px")
    print(f"   Duration    : {duration:.2f} s  |  FPS: {fps}")
    print()

    try:
        subprocess.run(_build_cmd(use_nvenc=hw_accel), check=True)
    except subprocess.CalledProcessError as exc:
        if hw_accel:
            print("⚠  NVENC failed — retrying with libx264 ...")
            subprocess.run(_build_cmd(use_nvenc=False), check=True)
        else:
            raise RuntimeError("FFmpeg encoding failed") from exc

    print(f"\n✅  Done → {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="merger",
        description=(
            "Create a Loom-style 1080p video — screenshot background with "
            "a circular webcam overlay at the bottom-right corner."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("screenshot", help="Path to the background screenshot image")
    p.add_argument("webcam",     help="Path to the webcam / face-cam video")
    p.add_argument("output",     help="Path for the output MP4 video")

    g = p.add_argument_group("overlay")
    g.add_argument("--circle-size",  type=int,   default=280,
                   help="Diameter of the circular webcam overlay (px)")
    g.add_argument("--margin",       type=int,   default=30,
                   help="Distance from right/bottom edge (px)")
    g.add_argument("--border-width", type=int,   default=5,
                   help="Width of the solid border ring (px)")
    g.add_argument("--border-color", default="white",
                   help="Border colour — named colour or #RRGGBB hex")
    g.add_argument("--no-shadow",    action="store_true",
                   help="Disable the drop-shadow behind the circle")

    g2 = p.add_argument_group("encoding")
    g2.add_argument("--fps",      type=int,   default=30,
                    help="Output frames per second")
    g2.add_argument("--duration", type=float, default=None,
                    help="Override output duration in seconds")
    g2.add_argument("--preset",   default="fast",
                    choices=["ultrafast", "superfast", "veryfast", "faster",
                             "fast", "medium", "slow"],
                    help="libx264 encoding preset (speed vs. file size)")
    g2.add_argument("--crf",      type=int,   default=23,
                    help="libx264 quality factor (18–28; lower = better)")
    g2.add_argument("--hw-accel", action="store_true",
                    help="Try NVENC GPU encoder (falls back to libx264)")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        create_loom_video(
            screenshot_path=args.screenshot,
            webcam_path=args.webcam,
            output_path=args.output,
            circle_size=args.circle_size,
            margin=args.margin,
            border_width=args.border_width,
            border_color=args.border_color,
            shadow=not args.no_shadow,
            fps=args.fps,
            duration=args.duration,
            hw_accel=args.hw_accel,
            preset=args.preset,
            crf=args.crf,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
