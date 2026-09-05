# Repository handoff

## Source baseline - 2026-09-05

`main` is the consolidated source baseline after the history-preserving promotion PR.
It is **not** an instruction to deploy, restart services or repoint production.

PixelSeal CLI plus the optional local image/video moderation tester. The tester is not wired into Desktop, mobile, backend job gating or RunPod. Verification: 35 unit tests passed; one opt-in real PixelSeal checkpoint integration test was not run. No model binaries, uploaded media or release artifacts are published by this promotion.

Read the [canonical stack manifest](https://github.com/gingerlabs-platform/telegram-bot/blob/main/STACK_MANIFEST.md)
and [promotion record](https://github.com/gingerlabs-platform/telegram-bot/blob/main/docs/MAIN-PROMOTION-20260905.md)
for the cross-repository refs, checks and deployment boundary.

The earlier handoff below is historical; its branch tips, test counts, endpoint releases
and temporary URLs are superseded where they differ from the records above.

Last reviewed: 2026-08-31

Read the canonical
[GingerLabs stack manifest](https://github.com/gingerlabs-platform/telegram-bot/blob/main/STACK_MANIFEST.md)
before changing shared PixelSeal assumptions or report integration contracts.

## Purpose

This public repository provides the standalone GingerLabs VideoSeal CLI. It
embeds and detects invisible PixelSeal watermark IDs in videos without needing
ComfyUI.

## Current state

- Working branch at handoff: `codex/nudenet-policy-tester`.
- Baseline commit before this handoff: `ee7e6dea5ca9`.
- Package version: `0.2.0`.
- The only accepted payload is `wm_v1_<22 Base64URL characters>`.
- Payloads use the current RS(32,16) encoding. The older text and repeated-bit
  formats are intentionally unsupported.
- The PixelSeal checkpoint is downloaded on demand, SHA-256 verified, and
  cached locally.
- The optional `gingerlabs_moderation` package is a local-only image and video policy
  experiment. It is not integrated with Desktop, backend job state, RunPod, or
  any production service.

## Important files

- `videoseal_cli/`: command implementation, payload codec, media handling, and
  vendored components.
- `scripts/`: release/build helpers.
- `tests/`: CLI, watermark, packaging, and media behavior tests.
- `pyproject.toml`: package metadata and console entry point.
- `videoseal-cli.spec`: PyInstaller release definition.
- `THIRD_PARTY_NOTICES.md`: redistributed component notices.
- `gingerlabs_moderation/`: CPU detector adapters, narrow policy, and local
  image/video upload interface. Video analysis samples at a bounded interval
  and removes its temporary local file immediately afterward.
- `Start Moderation Tester.cmd`: Windows one-click local tester launcher.

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

1. Read `README.md`, `docs/environment-setup.md`, `pyproject.toml`, and
   `THIRD_PARTY_NOTICES.md`.
2. Run the full unit suite.
3. Preserve canonical ID validation and checksum verification.
4. Never commit model checkpoints, generated release archives, or credentials.
5. Coordinate format changes with both video workers and the backend.
