from __future__ import annotations

import argparse
import io
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError

from .detectors import DetectorSuite
from .policy import PolicyConfig, evaluate_policy


MAX_FILES = 12
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
SUPPORTED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
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
    if len(payload) > MAX_FILE_BYTES:
        raise ValueError("Image is larger than 15 MB")
    try:
        with Image.open(io.BytesIO(payload)) as source:
            if source.width * source.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image exceeds the 40 megapixel safety limit")
            image = ImageOps.exif_transpose(source).convert("RGB")
            return np.asarray(image)
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("File is not a readable JPEG, PNG, or WebP image") from error


def create_app(suite_factory: Callable[[], DetectorSuite] = DetectorSuite) -> FastAPI:
    app = FastAPI(
        title="GingerLabs image moderation tester",
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
            "script-src 'self'; connect-src 'self'; object-src 'none'; "
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
    ) -> dict[str, object]:
        if not files or len(files) > MAX_FILES:
            return {"error": f"Choose between 1 and {MAX_FILES} images"}

        try:
            config = PolicyConfig(
                exact_parts_threshold=exact_parts_threshold,
                buttocks_threshold=buttocks_threshold,
                candidate_threshold=candidate_threshold,
            )
            config.validate()
        except ValueError as error:
            return {"error": str(error)}

        results: list[dict[str, object]] = []
        for index, upload in enumerate(files):
            filename = Path(upload.filename or "image").name
            if upload.content_type not in SUPPORTED_CONTENT_TYPES:
                results.append(
                    {"index": index, "filename": filename, "error": "Use a JPEG, PNG, or WebP image"}
                )
                continue
            try:
                payload = await upload.read(MAX_FILE_BYTES + 1)
                rgb_image = _decode_image(payload)
                height, width, _ = rgb_image.shape
                result = service.analyze(rgb_image, config)
                results.append(
                    {
                        "filename": filename,
                        "index": index,
                        "width": width,
                        "height": height,
                        **result,
                    }
                )
            except (RuntimeError, ValueError) as error:
                results.append({"index": index, "filename": filename, "error": str(error)})
            finally:
                await upload.close()

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
    parser = argparse.ArgumentParser(description="Run the local GingerLabs image moderation tester")
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
