# Third-Party Notices

This repository contains source code for a local PPTX-to-narrated-video pipeline. It does not bundle model weights, generated media, user voice samples, slide decks, or third-party binaries.

## Core runtime dependencies

Key dependencies include Python, PyYAML, Pydantic, python-pptx, Pillow, NumPy, SoundFile, librosa, PyTorch, torchaudio, transformers, accelerate, Hugging Face Hub, Gradio, ffmpeg, and LibreOffice. Verify the exact licenses of the versions you redistribute in your environment.

## VoxCPM2

The public build uses the `openbmb/VoxCPM2` model through the `voxcpm` Python package. The model weights and upstream package are not included in this repository. Before redistribution or commercial deployment, review the upstream model card, package license, and any usage restrictions that apply to your downloaded weights.

## Media and user data

Do not commit real slide decks, presenter notes containing private information, voice samples, generated audio, generated videos, API tokens, tunnel URLs, or local machine paths.
