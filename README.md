# pptx-voice-video

Local-first PowerPoint presenter-notes to narrated MP4 using a local VoxCPM2 voice-cloning backend.

This public repository contains source code only. It does **not** include slide decks, voice samples, generated audio/video, model weights, API tokens, or machine-specific artifacts.

## Features

- Extract presenter notes from `.pptx` files.
- Render slide visuals with LibreOffice, or use a PowerPoint-exported PDF as the visual source for higher fidelity.
- Generate narration with VoxCPM2 (`openbmb/VoxCPM2`) from a reference voice file.
- Normalize Korean/English technical lecture text with a configurable pronunciation dictionary.
- Compose FHD MP4 output with H.264/AAC via ffmpeg.
- Optional subtitles and conservative pointer overlay, both disabled by default.
- Resume-friendly audio cache and per-slide manifest/report files.
- Recorded-audio QC and semantic matching helpers for slide-specific overrides.

## Requirements

- Linux or macOS with Python 3.11+
- ffmpeg / ffprobe
- LibreOffice for PPTX rendering, unless using a PowerPoint-exported PDF visual source
- A CUDA-capable GPU is strongly recommended for VoxCPM2

## Installation

```bash
git clone https://github.com/wmyung/pptx-voice-video.git
cd pptx-voice-video
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

If your environment needs a custom PyTorch CUDA wheel, install PyTorch first following the official PyTorch instructions, then install this package.

## Minimal workflow

Prepare local inputs outside git-tracked paths, for example:

```text
local_inputs/
  lecture.pptx
  voice_reference.wav
  lecture_visuals_from_powerpoint.pdf   # optional, recommended for visual fidelity
local_outputs/
```

Run a short smoke test first:

```bash
pptx-voice-video render \
  --pptx local_inputs/lecture.pptx \
  --slide-visual-source local_inputs/lecture_visuals_from_powerpoint.pdf \
  --voice local_inputs/voice_reference.wav \
  --config example_config.yaml \
  --out local_outputs/smoke_1_3 \
  --engine voxcpm \
  --start-slide 1 --end-slide 3 \
  --no-subtitles \
  --no-pointer
```

Then render the full deck:

```bash
pptx-voice-video render \
  --pptx local_inputs/lecture.pptx \
  --slide-visual-source local_inputs/lecture_visuals_from_powerpoint.pdf \
  --voice local_inputs/voice_reference.wav \
  --config example_config.yaml \
  --out local_outputs/full \
  --engine voxcpm \
  --no-subtitles \
  --no-pointer
```

If you already know the desired duration, add automatic semantic retiming to the render command:

```bash
pptx-voice-video render \
  --pptx local_inputs/lecture.pptx \
  --slide-visual-source local_inputs/lecture_visuals_from_powerpoint.pdf \
  --voice local_inputs/voice_reference.wav \
  --config example_config.yaml \
  --out local_outputs/full \
  --engine voxcpm \
  --no-subtitles \
  --no-pointer \
  --target-minutes 70 \
  --retime-tempo 0.85 \
  --retime-slide-pause 3.0
```

The retimed copy is written under `local_outputs/full/retimed_70min/`.

Key outputs:

```text
local_outputs/full/final.mp4
local_outputs/full/manifest.json
local_outputs/full/report.json
local_outputs/full/notes_qc.json
local_outputs/full/audio_qc.json
```

## Retiming and natural pauses

If the raw TTS video is too short or the speech feels too fast, run a second retiming pass on the completed render `manifest.json`:

```bash
pptx-voice-video retime \
  --manifest local_outputs/full/manifest.json \
  --out local_outputs/full_70min \
  --target-minutes 70 \
  --tempo 0.85 \
  --slide-pause 3.0
```

This creates:

```text
local_outputs/full_70min/final_retimed.mp4
local_outputs/full_70min/retime_report.json
```

The retiming pass does **not** add pauses at arbitrary spaces, line breaks, or every detected micro-silence. It first selects semantic pause candidates from the normalized notes:

- sentence endings;
- question/emphasis endings;
- discourse shifts such as “however”, “therefore”, “first”, “next”, “finally”, “하지만”, “그래서”, “따라서”, “먼저”, “마지막으로”;
- long clause boundaries where a short pause is natural.

Then it aligns those semantic candidates to nearby actual breath/silence points in the audio when available. Dense list commas and clustered pause candidates are down-weighted to avoid a mechanical rhythm.

## VoxCPM2 configuration

`example_config.yaml` is VoxCPM2-only:

```yaml
tts:
  engine: voxcpm
  voxcpm:
    model_id: openbmb/VoxCPM2
    sample_rate: 48000
    max_chunk_chars: 260
    load_denoiser: false
    cfg_value: 2.0
    inference_timesteps: 10
    voice_control: null
    prompt_text: null
```

Notes:

- Keep `voice_control: null` when the reference audio already captures the desired style. Some TTS models may speak prepended style instructions if style control is implemented incorrectly.
- Provide `prompt_text` when you know the exact transcript of the voice reference. This can improve cloning and cadence matching.
- For dense slides, reduce `max_chunk_chars` if a long note causes out-of-memory or runaway synthesis.

## Korean/technical term pronunciation dictionary

The pipeline includes a configurable pronunciation dictionary. Entries are applied during text normalization before TTS synthesis, so technical terms can be read in the intended local pronunciation.

```yaml
text:
  language: ko
  pronunciation:
    GWAS: 지워스
    SNP: 스닙
    PRS: 피 알 에스
    LD: 엘 디
    eQTL: 이 큐 티 엘
    APOE: 아포이
```

Implementation details:

- ASCII terms are matched with word boundaries, so `AI` does not accidentally replace `AIX`.
- Korean postpositions after replaced ASCII terms are adjusted when possible: for example, `SNP가` with `SNP: 스닙` becomes `스닙이`.
- The dictionary lives in `text.pronunciation` in YAML, so each project can maintain its own term list.

## PowerPoint-exported PDF visual workflow

LibreOffice can render some PowerPoint decks differently from Microsoft PowerPoint. For important lecture videos, export the deck to PDF from PowerPoint and pass it as `--slide-visual-source` while still using the PPTX for presenter-note extraction.

## Quality checks

Inspect notes before a long render:

```bash
pptx-voice-video notes-qc \
  --pptx local_inputs/lecture.pptx \
  --out local_outputs/notes_qc.json \
  --config example_config.yaml
```

Run tests:

```bash
python -m pytest -q
```

Verify output media:

```bash
ffprobe -v error -show_entries \
  format=duration,size:stream=codec_name,codec_type,width,height,sample_rate,channels \
  -of json local_outputs/full/final.mp4
```

## Publication and privacy

Before publishing your own fork or outputs, ensure that you do not commit:

- slide decks or PDFs containing private content;
- voice samples or generated media;
- `sample_inputs/`, `sample_outputs/`, `local_inputs/`, or `local_outputs/`;
- API tokens, credentials, tunnel URLs, or local machine paths.

See `PUBLICATION_CHECKLIST.md` and `THIRD_PARTY_NOTICES.md`.
