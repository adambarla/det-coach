"""Text to speech for spoken questions and conversations.

The server renders audio with the macOS `say` command when it exists and caches it in
.cache/audio. On other systems /api/audio returns 404 and the browser falls back to the
Web Speech API, so the app works everywhere without extra installs.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
from functools import cache
from pathlib import Path

from .rounds import Line, Round

# Preferred macOS voices per role, best first. Apple's Premium and Enhanced versions of a
# voice sound far more natural, so any installed one wins over a basic voice.
MAC_VOICES = {
    "interviewer": ["Ava", "Zoe", "Samantha", "Allison"],
    "professor": ["Jamie", "Evan", "Nathan", "Daniel", "Tom"],
    "student": ["Zoe", "Ava", "Samantha", "Allison"],
    "student2": ["Serena", "Matilda", "Karen", "Moira"],
}
QUALITIES = ("Premium", "Enhanced", None)
VOICE_HELP = (
    "For natural voices, download a Premium voice such as Ava or Jamie in System "
    "Settings > Accessibility > Spoken Content > System Voice > Manage Voices."
)
_render_lock = threading.Lock()


def available() -> bool:
    return shutil.which("say") is not None


# `say -v ?` omits Premium and Enhanced voices on recent macOS, although `say` can use them.
# AVFoundation lists them, and JavaScript for Automation reaches it without extra installs.
_JXA = """ObjC.import("AVFoundation");
const v = $.AVSpeechSynthesisVoice.speechVoices, out = [];
for (let i = 0; i < v.count; i++) out.push(v.objectAtIndex(i).name.js);
out.join("\\n")"""


@cache
def installed_voices() -> frozenset[str]:
    """Full voice names that `say -v` accepts, e.g. "Daniel" or "Jamie (Premium)"."""
    voices = set()
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        # "Daniel (English (UK)) en_GB  # Hello!" is plain Daniel.
        if m := re.match(r"^(.+?)\s+[a-z]{2,3}_[A-Za-z0-9]+\s+#", line):
            voices.add(m.group(1).split(" (")[0])
    try:
        out = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", _JXA],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        voices.update(n for n in out.splitlines() if n.endswith(("(Premium)", "(Enhanced)")))
    except (OSError, subprocess.TimeoutExpired):
        pass
    return frozenset(voices)


def voice_for(role: str) -> str | None:
    names = MAC_VOICES.get(role, [])
    for quality in QUALITIES:
        for name in names:
            full = f"{name} ({quality})" if quality else name
            if full in installed_voices():
                return full
    return None


def has_natural_voice() -> bool:
    return any("(Premium)" in v or "(Enhanced)" in v for v in installed_voices())


def _say(text: str, role: str, out: Path) -> None:
    voice = voice_for(role)
    cmd = ["say", *(["-v", voice] if voice else []), "-o", str(out), text]
    subprocess.run(cmd, check=True, capture_output=True)


def render(lines: list[Line], out: Path) -> None:
    """Render one or more lines to an m4a file. Several lines need ffmpeg to join them."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, line in enumerate(lines):
            part = Path(tmp) / f"{i}.aiff"
            # A short silence after each turn, as in a real conversation.
            _say(line.text + (" [[slnc 450]]" if len(lines) > 1 else ""), line.voice, part)
            parts.append(part)
        if len(parts) == 1 or not shutil.which("ffmpeg"):
            if len(parts) > 1:  # no ffmpeg: one voice reads the whole conversation
                _say(" [[slnc 450]] ".join(x.text for x in lines), lines[0].voice, parts[0])
            cmd = ["afconvert", "-f", "m4af", "-d", "aac", str(parts[0]), str(out)]
        else:
            inputs = [arg for p in parts for arg in ("-i", str(p))]
            graph = "".join(f"[{i}:a]aresample=24000[a{i}];" for i in range(len(parts)))
            graph += "".join(f"[a{i}]" for i in range(len(parts)))
            graph += f"concat=n={len(parts)}:v=0:a=1[out]"
            cmd = [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                *inputs,
                "-filter_complex",
                graph,
                "-map",
                "[out]",
                "-c:a",
                "aac",
                str(out),
            ]
        subprocess.run(cmd, check=True, capture_output=True)


def _clips(rnd: Round) -> dict[str, list[Line]]:
    """Every audio file of a round by name: '<step>' for a whole step, '<step>.<n>' for one
    line of a step that plays its lines one at a time (Interactive Listening)."""
    out = {}
    for s in rnd.steps:
        if not s.listen or s.after:
            continue
        if s.type == "interactive_listening":
            out |= {f"{s.id}.{n}": [line] for n, line in enumerate(s.listen)}
        else:
            out[s.id] = s.listen
    return out


def audio_path(cache_dir: Path, rnd: Round, name: str) -> Path | None:
    """Return the cached audio for a step or clip, rendering it first if needed."""
    lines = _clips(rnd).get(name)
    if lines is None or not available():
        return None
    # The name hashes the text and voices, so edits and newly installed voices re-render.
    key = json.dumps([(voice_for(x.voice), x.text) for x in lines])
    out = cache_dir / rnd.id / f"{name}-{hashlib.sha1(key.encode()).hexdigest()[:10]}.m4a"
    with _render_lock:
        if not out.is_file():
            render(lines, out)
    return out


def prerender(cache_dir: Path, rnd: Round) -> None:
    """Render every spoken step in the background so the exam never waits."""

    def work() -> None:
        for name in _clips(rnd):
            try:
                audio_path(cache_dir, rnd, name)
            except (subprocess.CalledProcessError, OSError):
                return  # the browser falls back to Web Speech

    threading.Thread(target=work, daemon=True).start()
