# VideoSeal CLI

## Source baseline - 2026-09-05

`main` is the consolidated source baseline after the history-preserving promotion PR.
It is **not** an instruction to deploy, restart services or repoint production.

PixelSeal CLI plus the optional local image/video moderation tester. The tester is not wired into Desktop, mobile, backend job gating or RunPod. Verification: 35 unit tests passed; one opt-in real PixelSeal checkpoint integration test was not run. No model binaries, uploaded media or release artifacts are published by this promotion.

Read the [canonical stack manifest](https://github.com/gingerlabs-platform/telegram-bot/blob/main/STACK_MANIFEST.md)
and [promotion record](https://github.com/gingerlabs-platform/telegram-bot/blob/main/docs/MAIN-PROMOTION-20260905.md)
for the cross-repository refs, checks and deployment boundary.

Standalone CLI for embedding and detecting an invisible, Reed-Solomon-protected PixelSeal watermark ID directly in video pixels.

Release archives run on clean Windows, Linux, and macOS machines without ComfyUI, Python, or a system ffmpeg installation. The first embed, detect, or explicit doctor download fetches the PixelSeal checkpoint, verifies its SHA256, and caches it for later offline use.

## Commands

Embed a canonical 128-bit ID:

```bash
videoseal-cli embed \
  --input input.mp4 \
  --output output_watermarked.mp4 \
  --id wm_v1_k3qV9x7nB4mLp2ZaQ8fTdw \
  --copy-audio
```

Detect and optionally compare it:

```bash
videoseal-cli detect \
  --input output_watermarked.mp4 \
  --expected-id wm_v1_k3qV9x7nB4mLp2ZaQ8fTdw \
  --format both
```

Check the bundled runtime and model cache:

```bash
videoseal-cli doctor
videoseal-cli doctor --download-model
```

The low-impact embed defaults are PixelSeal, `scaling_w=0.15`, eight-frame chunks, full-resolution JND attenuation, and no temporal pooling. Advanced controls include:

```text
--scaling-w 0.15
--chunk-size 8
--full-resolution-jnd / --no-full-resolution-jnd
--temporal-pooling / --no-temporal-pooling
--temporal-pool-size 4
--temporal-pool-depth 2
```

## Payload

Only canonical IDs in this format are accepted:

```text
wm_v1_<22 unpadded Base64URL characters>
```

The suffix must decode to exactly 16 bytes. PixelSeal has a 256-bit message capacity, so the CLI encodes the 16 ID bytes with 16 Reed-Solomon parity bytes as an RS(32,16) codeword. Detection can correct up to eight corrupted bytes and reports `payload_encoding: "wm_v1_rs16"` after successful validation.

Version 0.2.0 intentionally removes arbitrary text/CRC payloads, the original repeated 128-bit format, and the older VideoSeal model.

## Model Cache

The PixelSeal checkpoint is approximately 1.24 GB:

```text
URL:    https://dl.fbaipublicfiles.com/videoseal/pixelseal/checkpoint.pth
SHA256: 0c5665cff20eb6ce1b5aaa7d91c19dafb418bfee32d02dd3344e4ed60d9d75bd
```

The cache defaults to `platformdirs.user_cache_dir("videoseal-cli", "GingerLabs") / "models"`.

- `--model-cache-dir PATH` selects a different cache.
- `--offline` requires an already verified checkpoint and performs no download.
- `--force-model-download` replaces and reverifies the PixelSeal checkpoint.

Older cached VideoSeal checkpoint files are ignored and are not deleted automatically.

## Development

```bash
python -m pip install -e . pyinstaller
python -m videoseal_cli --help
python -m unittest discover -s tests
```

Developer runs can use `ffmpeg` and `ffprobe` from `PATH`. Release archives bundle both tools. Third-party notices are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
Optional development/build environment paths are documented in
[`docs/environment-setup.md`](docs/environment-setup.md); the CLI has no
production service credentials.

## Local Media Moderation Tester

This repository also contains an isolated CPU-only experiment for the proposed
Wan output policy. It is not connected to GingerLabs Desktop, the backend,
RunPod, storage, or production.

On Windows, double-click:

```text
Start Moderation Tester.cmd
```

The first run creates a short-path environment under `%LOCALAPPDATA%\GLMod` to
avoid Windows package path limits, installs the optional dependencies,
downloads and SHA-256 verifies the pinned 5.2 MB exact-parts model, opens
`http://127.0.0.1:8765`. Images stay in memory. Videos are copied to a temporary
local file for seekable decoding and deleted immediately after analysis; no
media is uploaded or retained. The NudeNet 320n model is included by its Python
package. The first installation can take several minutes because the CPU
inference runtime is installed locally.

Manual setup is also supported:

```powershell
$moderationVenv = Join-Path $env:LOCALAPPDATA "GLMod\venv"
python -m venv $moderationVenv
& "$moderationVenv\Scripts\python.exe" -m pip install -e ".[moderation]"
& "$moderationVenv\Scripts\python.exe" -m gingerlabs_moderation
```

The experimental blocking policy is deliberately narrow:

- The exact-parts detector blocks `nipple`, `penis`, and `vagina`.
- NudeNet blocks `BUTTOCKS_EXPOSED`.
- NudeNet's broad `FEMALE_BREAST_EXPOSED` result is displayed as a diagnostic
  candidate but never blocks without an exact nipple detection.
- Every other NudeNet/exact-parts label is displayed as ignored and does not
  affect the verdict.

Thresholds are adjustable in the tester because the defaults are provisional.
The tester accepts JPEG, PNG, WebP, MP4, WebM, and MOV. Videos are sampled every
0.5 seconds by default, with a configurable 0.25–5 second interval and a hard
limit of 120 evenly distributed frames. A video is blocked when any sampled
frame blocks. This is sampled-frame evaluation, not proof that every video frame
is safe; production use still requires an explicit sampling and review policy.
Do not connect this policy to product delivery until it has been evaluated on a
representative, rights-cleared dataset containing both target content and hard
negatives such as cleavage, swimwear, side breast, underboob, and skin-toned
clothing.
