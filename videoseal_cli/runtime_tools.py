from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def executable_name(name: str) -> str:
    if os.name == "nt" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name


def bundled_base_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            dirs.append(Path(meipass))
        dirs.append(Path(sys.executable).resolve().parent)
    dirs.append(Path(__file__).resolve().parent)
    return dirs


def resolve_tool(name: str) -> str:
    exe = executable_name(name)
    env_dir = os.environ.get("VIDEOSEAL_CLI_FFMPEG_DIR")
    search_dirs = []
    if env_dir:
        search_dirs.append(Path(env_dir).expanduser())
    for base in bundled_base_dirs():
        search_dirs.extend([base, base / "bin", base / "tools", base / "ffmpeg"])

    for directory in search_dirs:
        candidate = directory / exe
        if candidate.is_file():
            return str(candidate)

    path_match = shutil.which(exe)
    if path_match:
        return path_match
    raise RuntimeError(
        f"could not find bundled {name}; set VIDEOSEAL_CLI_FFMPEG_DIR or install a release archive "
        f"that includes {exe}"
    )
