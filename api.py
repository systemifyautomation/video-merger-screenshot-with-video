#!/usr/bin/env python3
"""
Video Merger — REST API
=======================
Wraps merger.py in a FastAPI server.

Endpoints
---------
POST /merge
    Accepts a screenshot + webcam video upload and returns the merged MP4.

Authentication
--------------
All requests must include the header:
    X-Api-Key: <your API key>

The key is set via the API_KEY environment variable.

Example
-------
    curl -X POST https://upwork-video-merger.systemifyautomation.com/merge \\
        -H "X-Api-Key: YOUR_KEY" \\
        -F "screenshot=@screenshot.png" \\
        -F "webcam=@webcam.mkv" \\
        --output output.mp4
"""

import hmac
import os
import shutil
import tempfile

import uvicorn
from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from merger import create_loom_video

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Video Merger API",
    description="Loom-style video composer: screenshot background + circular webcam overlay.",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _verify_api_key(provided: str) -> None:
    """Raise 401 if the provided key does not match the configured API_KEY."""
    expected = os.environ.get("API_KEY", "")
    if not expected:
        raise HTTPException(status_code=500, detail="API_KEY environment variable is not set.")
    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status_code=401, detail="Invalid API key.")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Simple liveness check — no auth required."""
    return {"status": "ok"}


@app.post("/merge", response_class=FileResponse)
async def merge(
    screenshot: UploadFile = File(..., description="Background screenshot (PNG / JPG / …)"),
    webcam: UploadFile = File(..., description="Webcam video (MP4 / MKV / MOV / …)"),
    x_api_key: str = Header(..., alias="X-Api-Key"),
    # Overlay options
    circle_size: int = Query(280, description="Webcam circle diameter in px"),
    margin: int = Query(30, description="Distance from right/bottom edge in px"),
    border_width: int = Query(5, description="Border ring width in px"),
    border_color: str = Query("white", description="Border colour (named or #RRGGBB)"),
    shadow: bool = Query(True, description="Enable drop-shadow"),
    # Encoding options
    fps: int = Query(30, description="Output FPS"),
    preset: str = Query("fast", description="libx264 preset"),
    crf: int = Query(23, description="libx264 CRF quality (18–28)"),
) -> FileResponse:
    """
    Merge a screenshot and webcam video into a Loom-style 1080p MP4.

    Returns the output MP4 as a file download.
    """
    _verify_api_key(x_api_key)

    tmp = tempfile.mkdtemp(prefix="merger_")
    try:
        screenshot_path = os.path.join(tmp, "screenshot" + _ext(screenshot.filename))
        webcam_path = os.path.join(tmp, "webcam" + _ext(webcam.filename))
        output_path = os.path.join(tmp, "output.mp4")

        # Save uploads to temp directory
        for src, dest in ((screenshot, screenshot_path), (webcam, webcam_path)):
            with open(dest, "wb") as f:
                shutil.copyfileobj(src.file, f)

        create_loom_video(
            screenshot_path,
            webcam_path,
            output_path,
            circle_size=circle_size,
            margin=margin,
            border_width=border_width,
            border_color=border_color,
            shadow=shadow,
            fps=fps,
            preset=preset,
            crf=crf,
        )

        # Stream the file back; clean up temp dir after response is sent
        return FileResponse(
            output_path,
            media_type="video/mp4",
            filename="output.mp4",
            background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True),
        )

    except HTTPException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    except FileNotFoundError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ext(filename: str | None) -> str:
    """Return the file extension (including dot), or empty string."""
    if not filename:
        return ""
    return os.path.splitext(filename)[1].lower()


# ---------------------------------------------------------------------------
# Entrypoint (local dev)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
