from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from typing import Any

import numpy as np
import soundfile as sf

from .base import SynthesisOptions
from ..text_normalizer import chunk_text


class VoxCPMBackend:
    name = "voxcpm"

    def __init__(self, config):
        self.config = config
        self._model = None

    def supports_streaming(self) -> bool:
        return True

    def supports_voice_cloning(self) -> bool:
        return True

    def clone_or_prepare_voice(self, reference_audio: list[Path], cache_dir: Path) -> dict[str, Any]:
        cache_dir.mkdir(parents=True, exist_ok=True)
        return {"reference_audio": [str(p) for p in reference_audio]}

    def health_check(self) -> dict[str, Any]:
        report = {
            "engine": self.name,
            "model": self.config.model_path or self.config.model_id,
            "sample_rate": self.config.sample_rate,
        }
        try:
            import torch

            report.update({"torch": torch.__version__, "cuda_available": torch.cuda.is_available()})
            if torch.cuda.is_available():
                report["gpu"] = torch.cuda.get_device_name(0)
        except Exception as exc:
            report["torch_error"] = str(exc)
        try:
            import voxcpm  # noqa: F401

            report["voxcpm_installed"] = True
        except Exception as exc:
            report["voxcpm_installed"] = False
            report["voxcpm_error"] = str(exc)
        return report

    def _load(self):
        if self._model is not None:
            return
        from voxcpm import VoxCPM

        model_id = self.config.model_path or self.config.model_id
        self._model = VoxCPM.from_pretrained(
            model_id,
            load_denoiser=self.config.load_denoiser,
        )

    def _text_with_control(self, text: str, options: SynthesisOptions) -> str:
        # VoxCPM2 does not expose a separate natural-language style-control
        # argument.  Prepending style text to the target text makes the model
        # speak the instruction itself, so only synthesize the slide notes.
        return text

    def _generation_kwargs(self, options: SynthesisOptions) -> dict[str, Any]:
        kwargs = {
            "cfg_value": self.config.cfg_value,
            "inference_timesteps": self.config.inference_timesteps,
        }
        kwargs.update(self.config.generation)
        kwargs.update(options.generation)
        kwargs.pop("voice_control", None)
        kwargs.pop("prompt_text", None)
        return {k: v for k, v in kwargs.items() if v is not None}

    def _sample_rate(self) -> int:
        model_sr = getattr(getattr(self._model, "tts_model", None), "sample_rate", None)
        return int(model_sr or self.config.sample_rate)

    def _generate_one(
        self,
        text: str,
        reference_audio: list[Path],
        output_path: Path,
        options: SynthesisOptions,
    ) -> Path:
        self._load()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        refs = [Path(p) for p in reference_audio]
        kwargs = self._generation_kwargs(options)
        prompt_text = options.generation.get("prompt_text") or self.config.prompt_text
        if refs:
            kwargs["reference_wav_path"] = str(refs[0])
            if prompt_text:
                kwargs["prompt_wav_path"] = str(refs[0])
                kwargs["prompt_text"] = prompt_text
        result = self._model.generate(text=self._text_with_control(text, options), **kwargs)
        if isinstance(result, (str, Path)):
            data, sr = sf.read(result, dtype="float32")
            sf.write(output_path, data, sr)
            return output_path
        if isinstance(result, tuple):
            audio = result[0]
            sr = int(result[1]) if len(result) > 1 and isinstance(result[1], int) else self._sample_rate()
        elif isinstance(result, dict):
            audio = None
            for key in ("audio", "wav", "waveform", "speech"):
                if key in result:
                    audio = result[key]
                    break
            sr = int(result.get("sample_rate") or result.get("sampling_rate") or result.get("sr") or self._sample_rate())
        else:
            audio = result
            sr = self._sample_rate()
        arr = np.asarray(audio, dtype=np.float32).squeeze()
        if arr.ndim > 1:
            arr = arr[0]
        peak = float(np.max(np.abs(arr))) if arr.size else 0.0
        if peak > 1.0:
            arr = arr / peak
        sf.write(output_path, arr, sr)
        return output_path

    def synthesize(
        self,
        text: str,
        reference_audio: list[Path],
        output_path: Path,
        options: SynthesisOptions,
    ) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        chunks = chunk_text(text, max_chars=self.config.max_chunk_chars) or [text]
        if len(chunks) == 1:
            return self._generate_one(chunks[0], reference_audio, output_path, options)
        tmp = Path(tempfile.mkdtemp(prefix="voxcpm_chunks_"))
        parts = []
        for i, chunk in enumerate(chunks):
            parts.append(self._generate_one(chunk, reference_audio, tmp / f"part_{i:03}.wav", options))
        listfile = tmp / "list.txt"
        listfile.write_text(
            "".join(f"file '{str(p).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for p in parts),
            encoding="utf-8",
        )
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile), "-ar", str(options.sample_rate), str(output_path)],
            check=True,
        )
        return output_path
