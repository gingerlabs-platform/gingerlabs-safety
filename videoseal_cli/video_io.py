import json
import math
import os
import subprocess
from pathlib import Path

from .runtime_tools import resolve_tool


def read_video_rgb(path: Path):
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Missing numpy dependency. Install dependencies or use a standalone binary release.") from exc

    metadata = probe_video(path)
    width = int(metadata["width"])
    height = int(metadata["height"])
    fps = float(metadata["fps"])
    ffmpeg = resolve_tool("ffmpeg")
    command = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-vsync",
        "0",
        "-",
    ]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg failed to decode video {path}:\n{stderr}")

    frame_size = width * height * 3
    if not result.stdout or len(result.stdout) % frame_size != 0:
        raise RuntimeError(f"decoded raw video size is invalid for {width}x{height}: {len(result.stdout)} bytes")
    frame_count = len(result.stdout) // frame_size
    frames = np.frombuffer(result.stdout, dtype=np.uint8).reshape((frame_count, height, width, 3)).copy()
    return frames, fps


def probe_video(path: Path) -> dict:
    ffprobe = resolve_tool("ffprobe")
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames,duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}:\n{result.stderr}")
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError(f"no video stream found in {path}")
    stream = streams[0]
    fps = parse_rate(stream.get("avg_frame_rate")) or parse_rate(stream.get("r_frame_rate")) or 30.0
    return {"width": int(stream["width"]), "height": int(stream["height"]), "fps": fps}


def parse_rate(value: str | None) -> float | None:
    if not value or value == "0/0":
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_value = float(denominator)
        if math.isclose(denominator_value, 0.0):
            return None
        return float(numerator) / denominator_value
    return float(value)


def write_video_rgb_h264(frames, path: Path, fps: float, crf: int, pix_fmt: str, codec: str,
                         preset: str) -> None:
    if frames.ndim != 4 or frames.shape[-1] != 3:
        raise ValueError(f"expected [F,H,W,3] RGB frames, got {tuple(frames.shape)}")

    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count, height, width, _ = frames.shape
    encoder = "libx264" if codec in {"h264", "libx264"} else codec
    ffmpeg = resolve_tool("ffmpeg")
    command = [
        ffmpeg,
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps:.6f}",
        "-i",
        "-",
        "-an",
        "-c:v",
        encoder,
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        pix_fmt,
        str(path),
    ]

    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for index in range(frame_count):
            process.stdin.write(frames[index].tobytes())
        process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        return_code = process.wait()
    except BrokenPipeError as exc:
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        process.wait()
        raise RuntimeError(f"ffmpeg encoder failed while writing {path}:\n{stderr}") from exc

    if return_code != 0:
        raise RuntimeError(f"ffmpeg encoder failed with exit code {return_code} while writing {path}:\n{stderr}")


def mux_audio_from_source(video_without_audio: Path, source_with_audio: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = resolve_tool("ffmpeg")
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(video_without_audio),
        "-i",
        str(source_with_audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-shortest",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio mux failed with exit code {result.returncode}:\n{result.stderr}")


def move_video(video_without_audio: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    os.replace(video_without_audio, output)
