# Repository handoff

Last reviewed: 2026-08-23

## Purpose

This public repository provides the standalone GingerLabs VideoSeal CLI. It
embeds and detects invisible PixelSeal watermark IDs in videos without needing
ComfyUI.

## Current state

- Working branch at handoff: `main`.
- Baseline commit before this handoff: `ee7e6dea5ca9`.
- Package version: `0.2.0`.
- The only accepted payload is `wm_v1_<22 Base64URL characters>`.
- Payloads use the current RS(32,16) encoding. The older text and repeated-bit
  formats are intentionally unsupported.
- The PixelSeal checkpoint is downloaded on demand, SHA-256 verified, and
  cached locally.

## Important files

- `videoseal_cli/`: command implementation, payload codec, media handling, and
  vendored components.
- `scripts/`: release/build helpers.
- `tests/`: CLI, watermark, packaging, and media behavior tests.
- `pyproject.toml`: package metadata and console entry point.
- `videoseal-cli.spec`: PyInstaller release definition.
- `THIRD_PARTY_NOTICES.md`: redistributed component notices.

## Local verification

```powershell
python -m pip install -e . pyinstaller
python -m unittest discover -s tests
python -m videoseal_cli --help
python -m videoseal_cli doctor
```

Release artifacts must also be exercised on clean Windows, Linux, and macOS
systems because they bundle `ffmpeg` and `ffprobe`.

## Compatibility contract

The Telegram/Desktop backends derive the `wm_v1_...` identifier and workers
embed it. This CLI is the public decoder. Any payload-format change therefore
requires coordinated worker, backend, CLI, and reporting-flow updates. Do not
claim a video can be decoded unless its generation worker actually embedded
the current payload.

## Resume checklist

1. Read `README.md`, `pyproject.toml`, and `THIRD_PARTY_NOTICES.md`.
2. Run the full unit suite.
3. Preserve canonical ID validation and checksum verification.
4. Never commit model checkpoints, generated release archives, or credentials.
5. Coordinate format changes with both video workers and the backend.
