from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Protocol

import numpy as np
from platformdirs import user_cache_dir

from .policy import Detection


ERAX_REPOSITORY = "erax-ai/EraX-Anti-NSFW-V1.1"
ERAX_REVISION = "90878ab981060833413ae1a24df72f5e1fff66bc"
ERAX_FILENAME = "erax-anti-nsfw-yolo11n-v1.1.pt"
ERAX_SHA256 = "2df45339e529097f2aaca26fb5a56a0e8f01bafa0ded4cec6cc48ff3aba84eb2"
ERAX_DOWNLOAD_URL = (
    f"https://huggingface.co/{ERAX_REPOSITORY}/resolve/{ERAX_REVISION}/{ERAX_FILENAME}"
)


class Detector(Protocol):
    def detect(self, rgb_image: np.ndarray, minimum_score: float) -> list[Detection]: ...


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_parts_model_path(cache_root: Path | None = None) -> Path:
    root = cache_root or Path(
        os.environ.get(
            "GINGERLABS_MODERATION_CACHE",
            user_cache_dir("gingerlabs-moderation", "GingerLabs"),
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    target = root / ERAX_REVISION / ERAX_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and _sha256(target) == ERAX_SHA256:
        return target

    request = urllib.request.Request(
        ERAX_DOWNLOAD_URL,
        headers={"User-Agent": "GingerLabs-Moderation-Tester/0.1"},
    )
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            with urllib.request.urlopen(request, timeout=90) as response:
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
        if _sha256(temporary_path) != ERAX_SHA256:
            raise RuntimeError("Downloaded exact-parts model failed SHA-256 verification")
        temporary_path.replace(target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target


def _xywh_to_xyxy(box: list[float] | tuple[float, ...]) -> tuple[int, int, int, int]:
    x, y, width, height = box
    return (round(x), round(y), round(x + width), round(y + height))


class NudeNetAdapter:
    def __init__(self) -> None:
        try:
            from nudenet import NudeDetector
        except ImportError as error:
            raise RuntimeError(
                "NudeNet is not installed. Run pip install -e '.[moderation]'."
            ) from error
        self._detector = NudeDetector()

    def detect(self, rgb_image: np.ndarray, minimum_score: float) -> list[Detection]:
        bgr_image = rgb_image[:, :, ::-1].copy()
        raw_detections = self._detector.detect(bgr_image)
        return [
            Detection(
                detector="nudenet",
                label=str(item["class"]),
                score=float(item["score"]),
                box=_xywh_to_xyxy(item["box"]),
            )
            for item in raw_detections
            if float(item["score"]) >= minimum_score
        ]


class ExactPartsAdapter:
    def __init__(self, cache_root: Path | None = None) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError(
                "The exact-parts detector is not installed. Run pip install -e '.[moderation]'."
            ) from error
        self._model = YOLO(str(exact_parts_model_path(cache_root)))

    def detect(self, rgb_image: np.ndarray, minimum_score: float) -> list[Detection]:
        results = self._model.predict(
            source=rgb_image,
            conf=minimum_score,
            device="cpu",
            verbose=False,
        )
        detections: list[Detection] = []
        for result in results:
            names = result.names
            for box in result.boxes:
                class_id = int(box.cls[0].item())
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    Detection(
                        detector="exact_parts",
                        label=str(names[class_id]).strip().lower(),
                        score=float(box.conf[0].item()),
                        box=(round(x1), round(y1), round(x2), round(y2)),
                    )
                )
        return detections


class DetectorSuite:
    def __init__(self, cache_root: Path | None = None) -> None:
        self._nudenet = NudeNetAdapter()
        self._exact_parts = ExactPartsAdapter(cache_root)

    def detect(self, rgb_image: np.ndarray, minimum_score: float) -> list[Detection]:
        return [
            *self._nudenet.detect(rgb_image, minimum_score),
            *self._exact_parts.detect(rgb_image, minimum_score),
        ]
