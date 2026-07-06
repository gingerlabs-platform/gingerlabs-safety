# VideoSeal CLI

Standalone CLI for embedding and detecting an invisible text VideoSeal watermark ID directly in video pixels.

The release builds are intended to run on clean Windows, Linux, and macOS machines without ComfyUI, Python, or a system ffmpeg install. First use downloads the default VideoSeal checkpoint into a user cache and verifies its SHA256.

## Commands

```bash
videoseal-cli embed \
  --input input.mp4 \
  --output output_watermarked.mp4 \
  --id watermark-id-001 \
  --scaling-w 0.2 \
  --chunk-size 16 \
  --step-size 4 \
  --video-mode repeat \
  --crf 12 \
  --copy-audio
```

```bash
videoseal-cli detect \
  --input output_watermarked.mp4 \
  --expected-id watermark-id-001 \
  --chunk-size 16 \
  --aggregation avg \
  --format both
```

```bash
videoseal-cli doctor
videoseal-cli doctor --download-model
```

## Model Cache

Default model:

```text
https://dl.fbaipublicfiles.com/videoseal/y_256b_img.pth
```

Expected SHA256:

```text
3d2ff2523d2a89e3532c6dfdcf693098799326e9b3e74c185e815e9baa8340a3
```

Cache directory defaults to `platformdirs.user_cache_dir("videoseal-cli", "GingerLabs") / "models"`.

Useful flags:

- `--model-cache-dir PATH` uses a custom cache directory.
- `--offline` refuses network access and requires the checkpoint to already be cached.
- `--force-model-download` redownloads and reverifies the checkpoint.

## Payload Format

The current payload format stores the literal UTF-8 text from `--id` in the model bit capacity. For the default 256-bit model, the text can be at most 31 UTF-8 bytes.

When the text is 27 bytes or shorter, the payload includes CRC32 protection and detection reports `payload_encoding: text_crc32`. Text from 28 to 31 bytes is stored without CRC and detection reports `payload_encoding: text`.

The decoder also supports the older repeated 128-bit `wm_v1_<base64url>` format as a legacy fallback and reports `payload_encoding: wm_v1_legacy`.

## Development

For local Python development:

```bash
python -m pip install -e . pyinstaller
python -m videoseal_cli --help
python -m unittest discover -s tests
```

Developer runs may use `ffmpeg` and `ffprobe` from `PATH`. Release builds bundle those binaries.
