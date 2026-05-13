# video-merger-screenshot-with-video

Create **Loom-style 1080p videos** from a screenshot and a webcam clip —
the screenshot fills the background and the webcam appears in a **circular
frame at the bottom-right corner**, exactly like a Loom recording.

![demo frame](https://github.com/user-attachments/assets/e9858e5d-a50c-4f42-afc3-8763e22f4edc)

---

## Features

| Feature | Detail |
|---------|--------|
| **1080p output** | Fixed 1920 × 1080 H.264 MP4, web-optimised (`faststart`) |
| **Circular webcam overlay** | Pixel-perfect alpha-masked circle via FFmpeg `geq` filter |
| **Configurable** | Circle size, margin, border colour & width, drop-shadow |
| **Fast** | Pure FFmpeg pipeline — no Python frame loop |
| **GPU-optional** | `--hw-accel` tries NVENC, falls back to libx264 automatically |
| **Audio passthrough** | Webcam audio (if any) is included in the output |
| **Docker-ready** | Single `docker run` command — no local FFmpeg needed |

---

## Requirements

### Local

```bash
# 1. Install FFmpeg (system package)
# Ubuntu / Debian
sudo apt-get install -y ffmpeg

# macOS (Homebrew)
brew install ffmpeg

# 2. Install Python dependencies
pip install -r requirements.txt
```

### Docker

```bash
docker build -t merger .
```

---

## Usage

```bash
python merger.py SCREENSHOT WEBCAM OUTPUT [options]
```

### Positional arguments

| Argument | Description |
|----------|-------------|
| `SCREENSHOT` | Path to the background screenshot (PNG / JPG / …) |
| `WEBCAM` | Path to the webcam video (MP4 / MOV / …) |
| `OUTPUT` | Destination MP4 path |

### Options

```
Overlay:
  --circle-size INT    Diameter of the circular webcam overlay in px  [280]
  --margin INT         Distance from right/bottom edge in px           [30]
  --border-width INT   Width of the solid border ring in px            [5]
  --border-color STR   Border colour: named colour or #RRGGBB hex      [white]
  --no-shadow          Disable the drop-shadow behind the circle

Encoding:
  --fps INT            Output frames per second                        [30]
  --duration FLOAT     Override output duration in seconds
  --preset STR         libx264 preset (ultrafast…slow)                 [fast]
  --crf INT            libx264 quality factor (18–28)                  [23]
  --hw-accel           Try NVENC GPU encoder (falls back to libx264)
```

### Examples

```bash
# Basic usage
python merger.py screenshot.png webcam.mp4 output.mp4

# Larger circle, custom border colour, no shadow
python merger.py screenshot.png webcam.mp4 output.mp4 \
    --circle-size 320 --border-color "#4A90E2" --no-shadow

# Maximum encoding speed (large files, fast)
python merger.py screenshot.png webcam.mp4 output.mp4 \
    --preset ultrafast --crf 28

# High quality (smaller circle, best quality)
python merger.py screenshot.png webcam.mp4 output.mp4 \
    --circle-size 240 --preset slow --crf 18

# GPU encoding (NVIDIA)
python merger.py screenshot.png webcam.mp4 output.mp4 --hw-accel
```

### Docker

```bash
# Mount a local folder at /data and run
docker run --rm -v "$(pwd):/data" merger \
    /data/screenshot.png /data/webcam.mp4 /data/output.mp4 \
    --circle-size 300 --border-color "#FFFFFF"
```

---

## How it works

The script builds a single FFmpeg `filter_complex` graph:

```
screenshot (looped)  ──► scale 1920×1080 ──────────────────────┐
                                                                 ▼
webcam video  ──► scale NxN ──► geq (circular alpha mask) ──► overlay (bottom-right)
                                                                 │
                         (optional drop-shadow + border ring) ◄─┘
                                                                 ▼
                                                            1080p MP4
```

- **No Python frame loop** — FFmpeg handles all compositing natively for maximum speed.
- The **circular mask** is applied with FFmpeg's `geq` filter using `pow(X-r,2)+pow(Y-r,2) <= r^2`.
- The `moov` atom is placed at the front of the file (`+faststart`) so the video starts playing immediately in browsers / players.

---

## Running the tests

```bash
python tests/test_merger.py
```

Output:
```
▶  test_missing_input …
  ✅ Missing-input error handled gracefully

▶  test_no_shadow …
  ✅ --no-shadow flag works

▶  test_basic …
  ✅ Output: 1920×1080 h264, 3.00s

3/3 tests passed ✅
```
