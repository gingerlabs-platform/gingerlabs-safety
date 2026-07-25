from __future__ import annotations

import hashlib
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from platformdirs import user_cache_dir


MODEL_URL = "https://dl.fbaipublicfiles.com/videoseal/pixelseal/checkpoint.pth"
MODEL_FILENAME = "pixelseal_checkpoint.pth"
MODEL_SHA256 = "0c5665cff20eb6ce1b5aaa7d91c19dafb418bfee32d02dd3344e4ed60d9d75bd"
MODEL_SIZE_BYTES = 1_237_429_197


def default_model_cache_dir() -> Path:
    return Path(user_cache_dir("videoseal-cli", "GingerLabs")) / "models"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_file(path: Path) -> bool:
    return path.is_file() and sha256_file(path).lower() == MODEL_SHA256


def resolve_model_path(model_cache_dir: str | None, offline: bool, force_download: bool) -> Path:
    cache_dir = Path(model_cache_dir).expanduser() if model_cache_dir else default_model_cache_dir()
    cache_dir = cache_dir.resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / MODEL_FILENAME

    if model_path.exists() and not force_download:
        if verify_model_file(model_path):
            return model_path
        if offline:
            raise RuntimeError(f"cached model is corrupt and --offline was set: {model_path}")
        print(f"cached model failed SHA256 verification; redownloading: {model_path}", file=sys.stderr)
        model_path.unlink()

    if offline:
        raise RuntimeError(f"model is not cached and --offline was set: {model_path}")

    return download_model(model_path)


def download_model(model_path: Path) -> Path:
    temp_path = model_path.with_suffix(model_path.suffix + ".part")
    if temp_path.exists():
        temp_path.unlink()

    print(f"downloading PixelSeal checkpoint to {model_path}", file=sys.stderr)
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=30) as response, temp_path.open("wb") as output:
            expected = int(response.headers.get("Content-Length") or MODEL_SIZE_BYTES)
            downloaded = 0
            next_report = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if expected and downloaded >= next_report:
                    percent = downloaded / expected * 100
                    print(f"downloaded {downloaded / (1024 * 1024):.1f} MiB ({percent:.1f}%)", file=sys.stderr)
                    next_report += 25 * 1024 * 1024
    except (OSError, urllib.error.URLError) as exc:
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError(f"failed to download PixelSeal checkpoint from {MODEL_URL}: {exc}") from exc

    actual_hash = sha256_file(temp_path)
    if actual_hash.lower() != MODEL_SHA256:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(
            "downloaded PixelSeal checkpoint failed SHA256 verification: "
            f"expected {MODEL_SHA256}, got {actual_hash}"
        )

    os.replace(temp_path, model_path)
    print("PixelSeal checkpoint downloaded and verified", file=sys.stderr)
    return model_path
