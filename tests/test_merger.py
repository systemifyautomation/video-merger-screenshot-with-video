#!/usr/bin/env python3
"""
Smoke test for merger.py
Generates a dummy screenshot + dummy webcam video and verifies that
merger.py produces a valid 1080p MP4 output.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Make sure we can import the module
sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).resolve().parent.parent


def make_dummy_screenshot(path: str, width: int = 1920, height: int = 1080) -> None:
    """Create a simple coloured screenshot for testing."""
    img = Image.new("RGB", (width, height), color=(30, 60, 120))
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 100, 900, 500], fill=(255, 255, 255))
    img.save(path)


def make_dummy_webcam(path: str, duration: float = 3.0, fps: int = 30) -> None:
    """Create a solid-colour MP4 clip using FFmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x1a8a2e:size=640x480:rate={fps}:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        "-t", str(duration),
        path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def probe_video(path: str) -> dict:
    """Return basic video metadata via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-show_entries", "format=duration",
        "-of", "json",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_basic() -> None:
    """End-to-end: create a 1080p Loom-style video and verify dimensions."""
    with tempfile.TemporaryDirectory() as tmp:
        screenshot = os.path.join(tmp, "screenshot.png")
        webcam     = os.path.join(tmp, "webcam.mp4")
        output     = os.path.join(tmp, "output.mp4")

        print("  Creating dummy screenshot …")
        make_dummy_screenshot(screenshot)

        print("  Creating dummy webcam video …")
        make_dummy_webcam(webcam, duration=3.0)

        print("  Running merger.py …")
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "merger.py"),
             screenshot, webcam, output,
             "--circle-size", "200",
             "--margin", "20",
             "--fps", "30"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            raise AssertionError("merger.py exited with non-zero status")

        assert Path(output).exists(), "Output file was not created"
        assert Path(output).stat().st_size > 10_000, "Output file is suspiciously small"

        info = probe_video(output)
        streams = info.get("streams", [])
        assert streams, "No video streams found in output"
        stream = streams[0]
        assert stream["width"]  == 1920, f"Expected width 1920, got {stream['width']}"
        assert stream["height"] == 1080, f"Expected height 1080, got {stream['height']}"
        assert stream["codec_name"] == "h264", f"Expected h264, got {stream['codec_name']}"

        duration = float(info["format"]["duration"])
        assert 2.5 <= duration <= 3.5, f"Duration out of range: {duration:.2f}s"

        print(f"  ✅ Output: {stream['width']}×{stream['height']} h264, {duration:.2f}s")


def test_no_shadow() -> None:
    """Verify --no-shadow flag works without errors."""
    with tempfile.TemporaryDirectory() as tmp:
        screenshot = os.path.join(tmp, "screenshot.png")
        webcam     = os.path.join(tmp, "webcam.mp4")
        output     = os.path.join(tmp, "output_noshadow.mp4")

        make_dummy_screenshot(screenshot)
        make_dummy_webcam(webcam, duration=2.0)

        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "merger.py"),
             screenshot, webcam, output, "--no-shadow"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"merger.py failed:\n{result.stderr}"
        assert Path(output).exists()
        print("  ✅ --no-shadow flag works")


def test_missing_input() -> None:
    """Verify graceful error when an input file is missing."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "merger.py"),
         "/nonexistent/screenshot.png", "/nonexistent/webcam.mp4", "/tmp/out.mp4"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, "Expected non-zero exit for missing files"
    assert "not found" in result.stderr.lower() or "error" in result.stderr.lower()
    print("  ✅ Missing-input error handled gracefully")


if __name__ == "__main__":
    tests = [test_missing_input, test_no_shadow, test_basic]
    failed = 0
    for t in tests:
        print(f"\n▶  {t.__name__} …")
        try:
            t()
        except Exception as exc:
            print(f"  ❌ FAILED: {exc}")
            failed += 1
    if failed:
        print(f"\n{failed}/{len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"\n{len(tests)}/{len(tests)} tests passed ✅")
