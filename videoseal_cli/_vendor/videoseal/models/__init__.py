# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Inference-safe package initializer for the vendored VideoSeal modules.

The upstream initializer imports training and dataset paths. The CLI imports
the concrete submodules it needs directly to keep standalone binaries smaller
and free of ComfyUI/data-loader assumptions.
"""
