from __future__ import annotations

import argparse
import io
import math
import tempfile
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from .detectors import DetectorSuite
from .policy import PolicyConfig, evaluate_policy


MAX_FILES = 12
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_VIDEO_BYTES = 250 * 1024 * 1024
MAX_VIDEO_SECONDS = 10 * 60
MAX_SAMPLED_VIDEO_FRAMES = 120
MAX_IMAGE_PIXELS = 40_000_000
SUPPORTED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
SUPPORTED_VIDEO_CONTENT_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}
VIDEO_CONTENT_TYPE_SUFFIXES = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}
STATIC_ROOT = Path(__file__).with_name("static")


class ModerationService:
    def __init__(self, suite_factory: Callable[[], DetectorSuite]) -> None:
        self._suite_factory = suite_factory
        self._suite: DetectorSuite | None = None
        self._lock = threading.Lock()

    def analyze(self, rgb_image: np.ndarray, config: PolicyConfig) -> dict[str, object]:
        with self._lock:
            if self._suite is None:
                self._suite = self._suite_factory()
            minimum_score = min(
                config.candidate_threshold,
                config.exact_parts_threshold,
                config.buttocks_threshold,
            )
            detections = self._suite.detect(rgb_image, minimum_score)
        return evaluate_policy(detections, config).to_dict()


def _decode_image(payload: bytes) -> np.ndarray:
    if len(payload) > MAX_IMAGE_BYTES:
        raise ValueError("Image is larger than 15 MB")
    try:
        with Image.open(io.BytesIO(payload)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image exceeds the 40 megapixel safety limit")
            image = ImageOps.exif_transpose(source).convert("RGB")
            return np.asarray(image)
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("File is not a readable JPEG, PNG, or WebP image") from error


async def _stage_video(upload: UploadFile, suffix: str) -> Path:
    temporary = tempfile.NamedTemporaryFile(prefix="gingerlabs-moderation-", suffix=suffix, delete=False)
    target = Path(temporary.name)
    total = 0
    try:
        with temporary:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    raise ValueError("Video is larger than 250 MB")
                temporary.write(chunk)
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def _sample_frame_indices(frame_count: int, fps: float, interval_seconds: float) -> list[int]:
    if frame_count <= 0:
        return []
    step = max(1, round(fps * interval_seconds))
    indices = list(range(0, frame_count, step))
    if indices[-1] != frame_count - 1:
        indices.append(frame_count - 1)
    if len(indices) <= MAX_SAMPLED_VIDEO_FRAMES:
        return indices
    return sorted({
        round(index * (frame_count - 1) / (MAX_SAMPLED_VIDEO_FRAMES - 1))
        for index in range(MAX_SAMPLED_VIDEO_FRAMES)
    })


def _analyze_video(
    path: Path,
    service: ModerationService,
    config: PolicyConfig,
    interval_seconds: float,
) -> dict[str, object]:
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError("Video could not be opened. Use an MP4, WebM, or MOV with a standard video codec")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if (
            not math.isfinite(fps)
            or fps <= 0
            or frame_count <= 0
            or width <= 0
            or height <= 0
        ):
            raise ValueError("Video metadata could not be read")
        if width * height > MAX_IMAGE_PIXELS:
            raise ValueError("Video frames exceed the 40 megapixel safety limit")
        duration_seconds = frame_count / fps
        if duration_seconds > MAX_VIDEO_SECONDS:
            raise ValueError("Video is longer than 10 minutes")

        frames: list[dict[str, object]] = []
        for frame_index in _sample_frame_indices(frame_count, fps, interval_seconds):
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            readable, bgr_frame = capture.read()
            if not readable or bgr_frame is None:
                continue
            rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
            frame_result = service.analyze(rgb_frame, config)
            frames.append({
                "frameIndex": frame_index,
                "timestampSeconds": round(frame_index / fps, 3),
                **frame_result,
            })
        if not frames:
            raise ValueError("No readable video frames were found")

        blocked_frames = [frame for frame in frames if frame["decision"] == "block"]
        candidate_frames = [
            frame for frame in frames
            if any(detection["role"] == "candidate" for detection in frame["detections"])
        ]
        decision = "block" if blocked_frames else "allow"
        reasons = [
            (
                f"Blocking content was confirmed in {len(blocked_frames)} of "
                f"{len(frames)} sampled frames."
            )
            if blocked_frames
            else f"No configured blocking category was confirmed in {len(frames)} sampled frames."
        ]
        if candidate_frames and not blocked_frames:
            reasons.append(
                f"Broad exposed-breast candidates appeared in {len(candidate_frames)} sampled frames, "
                "without a nipple-specific confirmation."
            )
        return {
            "mediaType": "video",
            "width": width,
            "height": height,
            "durationSeconds": round(duration_seconds, 3),
            "sampleIntervalSeconds": interval_seconds,
            "sampledFrameCount": len(frames),
            "blockedFrameCount": len(blocked_frames),
            "decision": decision,
            "reasons": reasons,
            "frames": frames,
        }
    except cv2.error as error:
        raise ValueError("Video frames could not be decoded with the installed codecs") from error
    finally:
        capture.release()


def _media_kind(upload: UploadFile, filename: str) -> str | None:
    content_type = (upload.content_type or "").partition(";")[0].strip().lower()
    if content_type in SUPPORTED_IMAGE_CONTENT_TYPES:
        return "image"
    if content_type in SUPPORTED_VIDEO_CONTENT_TYPES:
        return "video"
    suffix = Path(filename).suffix.lower()
    if content_type in {"", "application/octet-stream"} and suffix in VIDEO_SUFFIXES:
        return "video"
    return None


def _video_suffix(upload: UploadFile, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return suffix
    content_type = (upload.content_type or "").partition(";")[0].strip().lower()
    return VIDEO_CONTENT_TYPE_SUFFIXES.get(content_type, ".mp4")


def create_app(suite_factory: Callable[[], DetectorSuite] = DetectorSuite) -> FastAPI:
    app = FastAPI(
        title="GingerLabs media moderation tester",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    service = ModerationService(suite_factory)
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    @app.middleware("http")
    async def local_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; media-src 'self' blob:; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": "local-only"}

    @app.post("/api/analyze")
    async def analyze(
        files: list[UploadFile] = File(...),
        exact_parts_threshold: float = Form(0.45),
        buttocks_threshold: float = Form(0.65),
        candidate_threshold: float = Form(0.35),
        video_sample_interval_seconds: float = Form(0.5),
    ) -> dict[str, object]:
        if not files or len(files) > MAX_FILES:
            return {"error": f"Choose between 1 and {MAX_FILES} files"}

        try:
            config = PolicyConfig(
                exact_parts_threshold=exact_parts_threshold,
                buttocks_threshold=buttocks_threshold,
                candidate_threshold=candidate_threshold,
            )
            config.validate()
            if not 0.25 <= video_sample_interval_seconds <= 5:
                raise ValueError("Video sampling interval must be between 0.25 and 5 seconds")
        except ValueError as error:
            return {"error": str(error)}

        results: list[dict[str, object]] = []
        for index, upload in enumerate(files):
            filename = Path(upload.filename or "image").name
            media_kind = _media_kind(upload, filename)
            if media_kind is None:
                results.append(
                    {
                        "index": index,
                        "filename": filename,
                        "error": "Use a JPEG, PNG, WebP, MP4, WebM, or MOV file",
                    }
                )
                continue
            temporary_path: Path | None = None
            try:
                if media_kind == "image":
                    payload = await upload.read(MAX_IMAGE_BYTES + 1)
                    rgb_image = _decode_image(payload)
                    height, width, _ = rgb_image.shape
                    result = {
                        "mediaType": "image",
                        "width": width,
                        "height": height,
                        **service.analyze(rgb_image, config),
                    }
                else:
                    temporary_path = await _stage_video(upload, _video_suffix(upload, filename))
                    result = _analyze_video(
                        temporary_path,
                        service,
                        config,
                        video_sample_interval_seconds,
                    )
                results.append(
                    {
                        "filename": filename,
                        "index": index,
                        **result,
                    }
                )
            except (RuntimeError, ValueError) as error:
                results.append({"index": index, "filename": filename, "error": str(error)})
            except OSError:
                results.append(
                    {
                        "index": index,
                        "filename": filename,
                        "error": "The local tester could not stage this file for analysis",
                    }
                )
            finally:
                await upload.close()
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)

        return {
            "policy": {
                "blocks": ["nipple", "penis", "vagina", "bare buttocks"],
                "doesNotBlock": [
                    "cleavage without a confirmed nipple",
                    "covered anatomy",
                    "male chest",
                    "belly",
                    "armpits",
                    "feet",
                    "faces",
                    "anus",
                    "sexual-act label",
                ],
            },
            "results": results,
        }

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local GingerLabs media moderation tester")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args()

    if not arguments.no_browser:
        threading.Timer(
            1.0,
            lambda: webbrowser.open(f"http://127.0.0.1:{arguments.port}"),
        ).start()

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=arguments.port, access_log=False)


if __name__ == "__main__":
    main()
