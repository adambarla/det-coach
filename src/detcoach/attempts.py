"""Attempts: one folder per sitting of a round.

attempts/<attempt-id>/
    attempt.json        manifest: round, start and finish time, one entry per saved step
    answers/<step>.txt  writing answers
    recordings/<step>.* speaking answers (webm from Chrome and Firefox, mp4 from Safari)
    transcripts.json    written by `det-coach transcribe`
    packet.md           written by `det-coach packet`, the grader's input
    feedback.json       written by the grader, shown on the results page
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

AUDIO_TYPES = {"audio/webm": ".webm", "audio/mp4": ".mp4", "audio/ogg": ".ogg"}
_lock = threading.Lock()


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Attempts:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path(self, attempt_id: str) -> Path:
        p = (self.root / attempt_id).resolve()
        if p.parent != self.root.resolve() or not (p / "attempt.json").is_file():
            raise FileNotFoundError(attempt_id)
        return p

    def manifest(self, attempt_id: str) -> dict:
        return json.loads((self.path(attempt_id) / "attempt.json").read_text(encoding="utf-8"))

    def _write(self, attempt_id: str, data: dict) -> None:
        (self.path(attempt_id) / "attempt.json").write_text(json.dumps(data, indent=2) + "\n")

    def create(self, round_id: str) -> str:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        attempt_id = f"{round_id}-{stamp}"
        n = 1
        while (self.root / attempt_id).exists():
            n += 1
            attempt_id = f"{round_id}-{stamp}-{n}"
        p = self.root / attempt_id
        p.mkdir(parents=True)
        manifest = {
            "id": attempt_id,
            "round": round_id,
            "started": now(),
            "finished": None,
            "steps": {},
        }
        (p / "attempt.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return attempt_id

    def save(
        self,
        attempt_id: str,
        step_id: str,
        data: bytes,
        content_type: str,
        final: bool,
        seconds: float | None = None,
    ) -> Path:
        """Write an answer. A draft (final=False) never replaces a submitted answer."""
        base = self.path(attempt_id)
        if content_type == "text/plain":
            out = base / "answers" / f"{step_id}.txt"
        elif content_type in AUDIO_TYPES:
            out = base / "recordings" / f"{step_id}{AUDIO_TYPES[content_type]}"
        else:
            raise ValueError(f"unsupported content type {content_type!r}")
        with _lock:
            m = self.manifest(attempt_id)
            if not final and step_id in m["steps"]:
                return out
            out.parent.mkdir(exist_ok=True)
            out.write_bytes(data)
            if final:
                m["steps"][step_id] = {
                    "saved": now(),
                    "file": str(out.relative_to(base)),
                    "seconds": seconds,
                }
                self._write(attempt_id, m)
        return out

    def finish(self, attempt_id: str) -> None:
        with _lock:
            m = self.manifest(attempt_id)
            m["finished"] = m["finished"] or now()
            self._write(attempt_id, m)

    def status(self, attempt_id: str) -> str:
        """in_progress, awaiting_feedback or graded. Grading writes feedback.json."""
        if (self.path(attempt_id) / "feedback.json").is_file():
            return "graded"
        return "awaiting_feedback" if self.manifest(attempt_id)["finished"] else "in_progress"

    def all(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        out = []
        for p in self.root.iterdir():
            if (p / "attempt.json").is_file():
                m = self.manifest(p.name)
                out.append(
                    {
                        "id": p.name,
                        "round": m["round"],
                        "started": m["started"],
                        "steps": len(m["steps"]),
                        "status": self.status(p.name),
                    }
                )
        return sorted(out, key=lambda a: a["started"], reverse=True)

    def resolve(self, ref: str) -> str:
        """Accept an attempt id, or 'latest' for the newest finished attempt."""
        if ref != "latest":
            self.path(ref)
            return ref
        for a in self.all():
            if a["status"] != "in_progress":
                return a["id"]
        raise FileNotFoundError("no finished attempt yet")
