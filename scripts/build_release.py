from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def platform_tag() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "x64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    if system == "darwin":
        system = "macos"
    return f"{system}-{machine}"


def run(command: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def archive_dir(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix == ".zip":
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in source.rglob("*"):
                archive.write(path, source.name / path.relative_to(source))
    else:
        with tarfile.open(output, "w:gz") as archive:
            archive.add(source, arcname=source.name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg-bin", required=True)
    parser.add_argument("--ffprobe-bin", required=True)
    parser.add_argument("--tag", default=platform_tag())
    args = parser.parse_args()

    env = os.environ.copy()
    env["FFMPEG_BIN"] = str(Path(args.ffmpeg_bin).resolve())
    env["FFPROBE_BIN"] = str(Path(args.ffprobe_bin).resolve())

    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    run(["pyinstaller", "--clean", "videoseal-cli.spec"], env=env)

    bundle = ROOT / "dist" / "videoseal-cli"
    suffix = ".zip" if platform.system().lower() == "windows" else ".tar.gz"
    archive_dir(bundle, ROOT / "release" / f"videoseal-cli-{args.tag}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
