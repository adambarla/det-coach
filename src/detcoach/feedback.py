"""Grading packet (the grader's input) and feedback.json validation (the grader's output).

The packet puts every prompt, answer, transcript and measure of one attempt in a single
Markdown file, so any coding agent can grade it without knowing this code base.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

from . import metrics
from .rounds import Round, Step
from .tasks import TASK_TYPES

WRITING_CRITERIA = ("content", "coherence", "grammar", "lexis")
SPEAKING_CRITERIA = (*WRITING_CRITERIA, "fluency", "pronunciation")
FIX_KEYS = ("original", "better", "why")


def marked_transcript(words: list[dict]) -> str:
    """Transcript text with pauses of 1 s or more shown inline, e.g. 'the [1.8 s] lab'."""
    out = [w["word"] for w in words[:1]]
    for prev, w in pairwise(words):
        if w["start"] - prev["end"] >= 1:
            out.append(f"[{w['start'] - prev['end']:.1f} s]")
        out.append(w["word"])
    return " ".join(out)


def _fmt_metrics(m: dict) -> str:
    return ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in m.items() if v not in ([], None))


def _prompt_block(step: Step, rnd: Round) -> list[str]:
    lines = []
    if step.photo:
        name = step.photo.rsplit("/", 1)[-1]
        meta = rnd.photos.get(name, {})
        lines += [
            f"Photo: `{rnd.path / 'photos' / name}` ({meta.get('title', '')}). "
            "Open the image file before grading content."
        ]
    if step.prompt:
        lines += [f"Prompt: {step.prompt}"]
    lines += [f"- {b}" for b in step.bullets]
    if step.listen:
        if step.type == "interactive_speaking":
            lines += [f"Question (heard once, not shown): {step.listen[0].text}"]
        else:
            lines += ["Conversation (heard once, not shown):"]
            lines += [f"> **{x.voice}:** {x.text}" for x in step.listen]
    return lines


def build_packet(rnd: Round, attempt_dir: Path, manifest: dict, transcripts: dict) -> str:
    out = [
        f"# Grading packet: {manifest['id']}",
        "",
        f"Round `{rnd.id}` ({rnd.title}), started {manifest['started']}.",
        "Grade it as `docs/grading.md` describes, against `rubric/rubric.md`.",
        f"Write `{attempt_dir / 'feedback.json'}` and run `det-coach check-feedback "
        f"{manifest['id']}`.",
        "",
    ]
    for step in rnd.steps:
        saved = manifest["steps"].get(step.id)
        spec = TASK_TYPES[step.type]
        timing = f"prep {step.prep} s, answer {step.answer} s"
        title = f"## `{step.id}` · {step.name}" + (f" · {step.part}" if step.part else "")
        out += [title, "", f"{spec.skill.title()} task, {timing}. Weight: {spec.weight}.", ""]
        out += _prompt_block(step, rnd) + [""]
        if not saved and (attempt_dir / "answers" / f"{step.id}.txt").is_file():
            out += [
                "_Not submitted: time ran out or the page closed. This is the last autosave._",
                "_Grade it, and say in its feedback that it was not submitted._",
                "",
            ]
            saved = {"file": f"answers/{step.id}.txt"}
        if not saved:
            out += ["_Not answered in this attempt. Skip it._", ""]
            continue
        if spec.skill == "writing":
            text = (attempt_dir / saved["file"]).read_text(encoding="utf-8")
            out += ["Answer:", "", "```text", text.strip() or "(empty)", "```", ""]
            out += [f"Measures: {_fmt_metrics(metrics.writing(text))}", ""]
        else:
            t = transcripts.get(step.id)
            if not t:
                out += ["_Recording not transcribed yet. Run `det-coach transcribe`._", ""]
                continue
            out += [
                "Transcript (Whisper, pauses of 1 s or more in brackets):",
                "",
                "```text",
                marked_transcript(t["words"]) or "(silence)",
                "```",
                "",
            ]
            out += [f"Measures: {_fmt_metrics(t['metrics'])}", ""]
    return "\n".join(out)


def _band(value, where: str, problems: list[str]) -> None:
    ok = (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(v, int) for v in value)
        and 10 <= value[0] <= value[1] <= 160
        and all(v % 5 == 0 for v in value)
    )
    if not ok:
        problems.append(f"{where}: band must be [low, high], multiples of 5 within 10 to 160")


def _criteria(crit, skill: str, where: str, p: list[str]) -> None:
    if not isinstance(crit, dict):
        p.append(f"{where}.criteria must be an object")
        return
    required = SPEAKING_CRITERIA if skill == "speaking" else WRITING_CRITERIA
    for c in crit:
        if c not in required:
            p.append(f"{where}.criteria: '{c}' is not a {skill} criterion")
    for c in required:
        v = crit.get(c, "missing")
        if v == "missing":
            p.append(f"{where}.criteria: '{c}' is missing (use null if you cannot judge it)")
        elif v is not None and not isinstance(v, dict):
            p.append(f"{where}.criteria.{c} must be an object or null")
        elif v is not None:
            _band(v.get("band"), f"{where}.criteria.{c}", p)
            if not v.get("note"):
                p.append(f"{where}.criteria.{c}: needs a 'note'")


def check(feedback, rnd: Round, manifest: dict) -> list[str]:
    """Return every problem in a feedback.json. An empty list means it is valid."""
    if not isinstance(feedback, dict):
        return ["feedback.json must hold an object"]
    p: list[str] = []
    if feedback.get("version") != 1:
        p.append("'version' must be 1")
    if feedback.get("attempt") != manifest["id"]:
        p.append(f"'attempt' must be '{manifest['id']}'")
    for key in ("grader", "summary"):
        if not isinstance(feedback.get(key), str) or not feedback.get(key):
            p.append(f"'{key}' must be a non-empty string")
    est = feedback.get("estimate", {})
    if not isinstance(est, dict):
        p.append("'estimate' must be an object")
        est = {}
    for skill in ("writing", "speaking"):
        if skill in est:
            _band(est[skill], f"estimate.{skill}", p)
    pri = feedback.get("priorities")
    if (
        not isinstance(pri, list)
        or not 1 <= len(pri) <= 3
        or not all(isinstance(x, dict) and x.get("title") and x.get("detail") for x in pri)
    ):
        p.append("'priorities' must list 1 to 3 objects with 'title' and 'detail'")
    steps = {s.id: s for s in rnd.steps}
    given = feedback.get("steps", {})
    if not isinstance(given, dict):
        return [*p, "'steps' must be an object with one entry per step id"]
    for sid in manifest["steps"]:
        if sid not in given:
            p.append(f"steps: answered step '{sid}' has no feedback")
    for sid, f in given.items():
        where = f"steps.{sid}"
        if sid not in steps:
            p.append(f"{where}: not a step of round {rnd.id}")
            continue
        if not isinstance(f, dict):
            p.append(f"{where} must be an object")
            continue
        _band(f.get("band"), where, p)
        _criteria(f.get("criteria"), steps[sid].skill, where, p)
        for key in ("strengths", "next_time"):
            if not isinstance(f.get(key, []), list):
                p.append(f"{where}.{key} must be a list")
        fixes = f.get("fixes", [])
        if not isinstance(fixes, list):
            p.append(f"{where}.fixes must be a list")
            continue
        for i, fix in enumerate(fixes):
            if not isinstance(fix, dict) or not all(fix.get(k) for k in FIX_KEYS):
                p.append(f"{where}.fixes[{i}]: needs 'original', 'better' and 'why'")
    return p


def load_feedback(attempt_dir: Path) -> dict | None:
    f = attempt_dir / "feedback.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
