"""Transcribe speaking answers with Whisper, locally.

Two backends: mlx-whisper on Apple Silicon (`uv sync --extra mlx`, needs ffmpeg on the
PATH) and faster-whisper everywhere else (`uv sync --extra whisper`). Audio never leaves
the machine.
"""

from __future__ import annotations

import functools
import json
import platform
from pathlib import Path

from . import metrics

# Whisper drops fillers unless the prompt shows that the transcript keeps them.
VERBATIM_PROMPT = "Umm, so, uh, I think, like... hmm. Okay, so, um, the thing is, uh, yeah."
# Whisper can invent repeated sentences in the silence after an answer. This skips them.
GUARDS = {"hallucination_silence_threshold": 2.0}
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
FW_MODEL = "large-v3-turbo"


class NoBackend(RuntimeError):
    pass


def _backend() -> str:
    try:
        import mlx_whisper  # noqa: F401

        return "mlx"
    except ImportError:
        pass
    try:
        import faster_whisper  # noqa: F401

        return "faster-whisper"
    except ImportError:
        pass
    extra = "mlx" if platform.machine() == "arm64" and platform.system() == "Darwin" else "whisper"
    raise NoBackend(f"No transcription backend installed. Run: uv sync --extra {extra}")


def _word(word: str, start, end, probability) -> dict:
    # Backends return numpy scalars, which json cannot write.
    return {
        "word": word.strip(),
        "start": round(float(start), 2),
        "end": round(float(end), 2),
        "probability": round(float(probability), 3),
    }


@functools.cache
def _faster_whisper(model: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model, device="auto", compute_type="auto")


def transcribe_file(path: Path, model: str | None = None) -> dict:
    """Return {"text", "words": [{"word", "start", "end", "probability"}]}."""
    if _backend() == "mlx":
        import mlx_whisper

        r = mlx_whisper.transcribe(
            str(path),
            path_or_hf_repo=model or MLX_MODEL,
            language="en",
            word_timestamps=True,
            initial_prompt=VERBATIM_PROMPT,
            **GUARDS,
        )
        words = [
            _word(w["word"], w["start"], w["end"], w.get("probability", 1))
            for seg in r["segments"]
            for w in seg.get("words", [])
        ]
    else:
        segs, _ = _faster_whisper(model or FW_MODEL).transcribe(
            str(path),
            language="en",
            word_timestamps=True,
            initial_prompt=VERBATIM_PROMPT,
            vad_filter=False,
            **GUARDS,
        )
        words = [_word(w.word, w.start, w.end, w.probability) for s in segs for w in s.words or []]
    return {"text": " ".join(w["word"] for w in words), "words": words}


def transcribe_attempt(
    attempt_dir: Path,
    slots: dict[str, int],
    model: str | None = None,
    force: bool = False,
    log=print,
) -> dict:
    """Transcribe every recording of an attempt into transcripts.json. Cached per step."""
    out = attempt_dir / "transcripts.json"
    done = json.loads(out.read_text()) if out.is_file() and not force else {}
    for rec in sorted((attempt_dir / "recordings").glob("*")):
        step = rec.stem
        if step in done:
            continue
        log(f"transcribing {rec.name}")
        t = transcribe_file(rec, model)
        t["metrics"] = metrics.speaking(t["words"], slots.get(step, 0))
        done[step] = t
        out.write_text(json.dumps(done, indent=1) + "\n")
    return done
