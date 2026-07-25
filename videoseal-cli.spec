# -*- mode: python ; coding: utf-8 -*-

import os
import shutil
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


def required_binary(env_name, fallback_name):
    value = os.environ.get(env_name)
    path = Path(value) if value else None
    if path is None:
        found = shutil.which(fallback_name)
        path = Path(found) if found else None
    if path is None or not path.is_file():
        raise SystemExit(f"Set {env_name} to a valid {fallback_name} binary before building")
    return str(path.resolve())


ffmpeg = required_binary("FFMPEG_BIN", "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
ffprobe = required_binary("FFPROBE_BIN", "ffprobe.exe" if os.name == "nt" else "ffprobe")

datas = []
datas += collect_data_files("videoseal_cli.videoseal_configs")
datas += collect_data_files("videoseal_cli._vendor.videoseal", includes=["LICENSE"])
datas += collect_data_files("videoseal_cli._vendor.reedsolo", includes=["LICENSE"])

binaries = [
    (ffmpeg, "."),
    (ffprobe, "."),
]

hiddenimports = []
hiddenimports += collect_submodules("timm")
hiddenimports += collect_submodules("videoseal_cli._vendor.videoseal.modules")
hiddenimports += collect_submodules("videoseal_cli._vendor.reedsolo")
hiddenimports += [
    "videoseal_cli._vendor.videoseal.models.blender",
    "videoseal_cli._vendor.videoseal.models.embedder",
    "videoseal_cli._vendor.videoseal.models.extractor",
]

a = Analysis(
    ["videoseal_cli/__main__.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "cv2",
        "decord",
        "pandas",
        "pycocotools",
        "tensorboard",
        "torchaudio",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="videoseal-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="videoseal-cli",
)
