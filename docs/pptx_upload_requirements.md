# Presenter-note requirements before uploading PPTX files

Use this checklist before rendering a narrated video. It reduces TTS mumbling, runaway generation, timing drift, and poor pronunciation.

## Recommended note length

- Keep each slide under about 900 normalized characters.
- A safer target is 300-600 characters per slide.
- Prefer sentences under 80-120 characters.
- Split slides whose narration would exceed about 3 minutes.

## Sentence structure

Good:

```text
This slide explains the core workflow.
First, we review the background concept.
Next, we summarize the procedure and the result.
```

Avoid:

```text
ConceptA→ConceptB / term / number↑ / item※reference
```

Write symbols and abbreviations as spoken text, or add them to the pronunciation dictionary.

## Symbols and numbers

Prefer natural spoken forms:

- `3-5 days` → `three to five days`
- `A/B` → `A and B`
- `v2.0` → `version two point zero`
- important abbreviations → pronunciation dictionary entries

## Stage directions

Stage directions such as `[pause]` or `(emphasize here)` can be stripped by configuration. If they should be spoken, rewrite them as normal narration.

## URLs, filenames, references

Do not place long URLs, filenames, DOI strings, or full references in presenter notes. Replace them with a spoken sentence such as “Detailed references are listed on the final slide.”

## Mixed-language technical talks

For English terms in non-English narration, add explicit pronunciation mappings in `example_config.yaml` or your job config:

```yaml
text:
  pronunciation:
    GWAS: 지워스
    SNP: 스닙
```

## When to use recorded slide audio

Use direct recorded audio overrides for slides where TTS quality is critical:

- many technical terms;
- long central explanation;
- dense numeric tables;
- audio QC reports `too_long`, `longer_than_expected`, `too_much_silence`, or `low_volume`.

Recognized override filenames include:

```text
recordings/
  24.m4a
  27.wav
  slide_030.mp3
```

Or provide a YAML mapping:

```yaml
slides:
  24: recordings/slide_024.m4a
  27: recordings/slide_027.wav
```

## QC commands

```bash
pptx-voice-video notes-qc \
  --pptx local_inputs/lecture.pptx \
  --config example_config.yaml \
  --out local_outputs/notes_qc.json

pptx-voice-video recorded-audio-qc \
  --pptx local_inputs/lecture.pptx \
  --recordings local_inputs/recordings \
  --config example_config.yaml \
  --out local_outputs/recorded_audio_qc.json
```
