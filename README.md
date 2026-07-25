# VideoSeal CLI

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
