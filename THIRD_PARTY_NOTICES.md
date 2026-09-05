# Third-Party Notices

## VideoSeal / PixelSeal

The inference implementation is derived from Meta Platforms, Inc. VideoSeal and is distributed under the MIT License. The complete notice is included at `videoseal_cli/_vendor/videoseal/LICENSE`.

## reedsolo 1.7.0

The bundled Reed-Solomon implementation is copyright Tomer Filiba, Stephen Larroque, and contributors. It is available under the Unlicense or MIT No Attribution License. The complete notice is included at `videoseal_cli/_vendor/reedsolo/LICENSE`.

## Optional local moderation dependencies

The image and video moderation tester installs these components only when the
`moderation` extra is selected. They are not bundled into VideoSeal CLI release
archives.

- NudeNet 3.4.2 and its 320n detector are distributed under AGPL-3.0 by the
  notAI-tech contributors.
- Ultralytics is distributed under AGPL-3.0 for open-source use. Its runtime is
  used to load the exact-parts detector.
- EraX Anti-NSFW V1.1 is distributed under Apache-2.0 by EraX and is downloaded
  from the pinned Hugging Face revision documented in
  `gingerlabs_moderation/detectors.py`.
- FastAPI, Uvicorn, Pillow, python-multipart, ONNX Runtime, and OpenCV retain
  their respective upstream licenses.

Commercial or network deployment requires a separate license-compliance
review. The current feature is a local evaluation tool only.
