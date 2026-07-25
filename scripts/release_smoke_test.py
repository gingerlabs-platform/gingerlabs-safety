from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


WATERMARK_ID = "wm_v1_k3qV9x7nB4mLp2ZaQ8fTdw"


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=True)


def executable_in(bundle_dir: Path) -> Path:
    name = "videoseal-cli.exe" if os.name == "nt" else "videoseal-cli"
    executable = bundle_dir.resolve() / name
    if not executable.is_file():
        raise FileNotFoundError(f"built executable not found: {executable}")
    return executable


def parse_json_stdout(result: subprocess.CompletedProcess[str], command_name: str) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{command_name} stdout was not valid JSON:\n{result.stdout}") from exc


def create_fixture(ffmpeg: Path, output: Path) -> None:
    run(
        [
            str(ffmpeg),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "mandelbrot=size=256x256:rate=8",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=1",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ]
    )


def assert_audio_stream(ffprobe: Path, video: Path) -> None:
    result = run(
        [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(video),
        ]
    )
    streams = json.loads(result.stdout).get("streams") or []
    if not streams or streams[0].get("codec_type") != "audio":
        raise AssertionError("watermarked output does not contain an audio stream")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--model-cache-dir", type=Path, required=True)
    parser.add_argument("--ffmpeg-bin", type=Path, required=True)
    parser.add_argument("--ffprobe-bin", type=Path, required=True)
    args = parser.parse_args()

    executable = executable_in(args.bundle_dir)
    args.model_cache_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pixelseal_release_smoke_") as temp_dir:
        temp = Path(temp_dir)
        source = temp / "source.mp4"
        watermarked = temp / "watermarked.mp4"
        create_fixture(args.ffmpeg_bin.resolve(), source)

        doctor = run(
            [
                str(executable),
                "doctor",
                "--download-model",
                "--model-cache-dir",
                str(args.model_cache_dir),
                "--format",
                "json",
            ]
        )
        doctor_result = parse_json_stdout(doctor, "doctor")
        if not doctor_result.get("ok"):
            raise AssertionError(f"doctor failed: {doctor_result}")
        for tool in ("ffmpeg", "ffprobe"):
            tool_path = Path(doctor_result["checks"][tool]["path"]).resolve()
            if not tool_path.is_relative_to(args.bundle_dir.resolve()):
                raise AssertionError(f"doctor resolved system {tool} instead of the bundled binary: {tool_path}")

        embed = run(
            [
                str(executable),
                "embed",
                "--input",
                str(source),
                "--output",
                str(watermarked),
                "--id",
                WATERMARK_ID,
                "--model-cache-dir",
                str(args.model_cache_dir),
                "--offline",
                "--device",
                "cpu",
                "--copy-audio",
            ]
        )
        embed_result = parse_json_stdout(embed, "embed")
        if embed_result.get("watermark_id") != WATERMARK_ID:
            raise AssertionError(f"embed returned the wrong ID: {embed_result}")
        assert_audio_stream(args.ffprobe_bin.resolve(), watermarked)

        detect = run(
            [
                str(executable),
                "detect",
                "--input",
                str(watermarked),
                "--expected-id",
                WATERMARK_ID,
                "--model-cache-dir",
                str(args.model_cache_dir),
                "--offline",
                "--device",
                "cpu",
                "--format",
                "json",
            ]
        )
        detect_result = parse_json_stdout(detect, "detect")
        expected = {
            "decoded_watermark_id": WATERMARK_ID,
            "match": True,
            "format_valid": True,
            "payload_encoding": "wm_v1_rs16",
            "bit_accuracy_percent": 100.0,
        }
        for key, value in expected.items():
            if detect_result.get(key) != value:
                raise AssertionError(f"detect returned {key}={detect_result.get(key)!r}, expected {value!r}")

    print("PixelSeal release smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
