"""Load practice rounds from rounds/<id>/round.json and expand them into timed steps.

A task is what a round file lists. A step is one timed screen. Most tasks are one step.
Interactive Writing is two steps and Interactive Speaking is one step per question.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from . import content
from .model import Line, Step
from .tasks import TASK_TYPES

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")  # also what the server accepts
VOICES = ("interviewer", "professor", "student", "student2")
PHOTO_FIELDS = ("title", "author", "license", "source")


class RoundError(ValueError):
    """A round file is invalid. `problems` lists every issue found."""

    def __init__(self, round_id: str, problems: list[str]):
        self.problems = problems
        super().__init__(f"{round_id}: " + "; ".join(problems))


@dataclass
class Round:
    id: str
    title: str
    path: Path
    photos: dict[str, dict]
    steps: list[Step]

    @property
    def minutes(self) -> int:
        # Prep and answer of every step, and about 15 s per task to read its intro screen.
        tasks = len({s.task for s in self.steps})
        return round((sum(s.prep + s.answer for s in self.steps) + 15 * tasks) / 60)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "steps": len(self.steps),
            "minutes": self.minutes,
        }

    def public(self) -> dict:
        return {**self.summary(), "steps": [asdict(s) for s in self.steps], "photos": self.photos}


def _require(task: dict, key: str, kind: type, problems: list[str], where: str) -> None:
    if not isinstance(task.get(key), kind) or not task.get(key):
        problems.append(f"{where}: needs a non-empty '{key}'")


def _check(data: dict, path: Path) -> list[str]:
    problems: list[str] = []
    if data.get("id") != path.name:
        problems.append(f"'id' must equal the folder name '{path.name}'")
    if not SLUG.match(path.name):
        problems.append("the folder name must be lowercase letters, digits and dashes")
    if not isinstance(data.get("title"), str) or not data["title"]:
        problems.append("needs a 'title'")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return problems + ["needs a non-empty 'tasks' list"]
    photos = data.get("photos", {})
    seen: set[str] = set()
    for i, task in enumerate(tasks):
        where = f"task {i + 1}"
        if not isinstance(task, dict):
            problems.append(f"{where}: must be an object")
            continue
        tid, ttype = task.get("id", ""), task.get("type", "")
        where = f"task '{tid or i + 1}'"
        if not SLUG.match(str(tid)):
            problems.append(f"{where}: 'id' must be lowercase letters, digits and dashes")
        if tid in seen:
            problems.append(f"{where}: duplicate id")
        seen.add(tid)
        if ttype not in TASK_TYPES:
            problems.append(f"{where}: unknown type '{ttype}' (known: {', '.join(TASK_TYPES)})")
            continue
        if ttype in ("write_photo", "speak_photo"):
            _require(task, "photo", str, problems, where)
            name = task.get("photo", "")
            if name and not FILE_NAME.match(name):
                problems.append(f"{where}: photo name '{name}' may use only letters, digits, . _ -")
            elif name and not (path / "photos" / name).is_file():
                problems.append(f"{where}: photo file photos/{name} is missing")
            meta = photos.get(name, {})
            missing = [f for f in PHOTO_FIELDS if not meta.get(f)]
            if name and missing:
                problems.append(f"{where}: photos['{name}'] needs {', '.join(missing)}")
        if ttype in ("interactive_writing", "writing_sample", "read_then_speak", "speaking_sample"):
            _require(task, "prompt", str, problems, where)
        if ttype == "interactive_writing":
            _require(task, "follow_up", str, problems, where)
        if ttype == "read_then_speak" and not isinstance(task.get("bullets", []), list):
            problems.append(f"{where}: 'bullets' must be a list of strings")
        if ttype == "summarize_conversation":
            lines = task.get("conversation")
            if not isinstance(lines, list) or len(lines) < 4:
                problems.append(f"{where}: 'conversation' needs at least 4 lines")
            else:
                for line in lines:
                    if line.get("speaker") not in VOICES or not line.get("text"):
                        problems.append(
                            f"{where}: each line needs 'speaker' in {VOICES} and 'text'"
                        )
                        break
        if ttype in content.CHECKS:
            problems += [f"{where}: {x}" for x in content.CHECKS[ttype](task)]
        if ttype == "interactive_speaking":
            topics = task.get("topics")
            if not isinstance(topics, list) or not topics:
                problems.append(f"{where}: 'topics' needs at least one topic")
            elif any(not t.get("questions") for t in topics):
                problems.append(f"{where}: every topic needs 'questions'")
    return problems


def _expand(task: dict, photo_url: str) -> list[Step]:
    ttype = task["type"]
    spec = TASK_TYPES[ttype]
    base = dict(task=task["id"], type=ttype, name=spec.name, skill=spec.skill)
    tid = task["id"]
    if ttype == "interactive_writing":
        return [
            Step(
                id=f"{tid}-1",
                prep=spec.prep,
                answer=spec.answer,
                part="Part 1 of 2",
                prompt=task["prompt"],
                **base,
            ),
            Step(
                id=f"{tid}-2",
                prep=0,
                answer=spec.follow_up_answer,
                part="Part 2 of 2",
                prompt=task["follow_up"],
                show_previous=f"{tid}-1",
                **base,
            ),
        ]
    if ttype in content.EXPANDERS:
        return content.EXPANDERS[ttype](task, spec, base)
    if ttype == "interactive_speaking":
        questions = [q for t in task["topics"] for q in t["questions"]]
        return [
            Step(
                id=f"{tid}-{n}",
                prep=0,
                answer=spec.answer,
                part=f"Question {n} of {len(questions)}",
                listen=[Line("interviewer", q)],
                **base,
            )
            for n, q in enumerate(questions, 1)
        ]
    step = Step(id=tid, prep=spec.prep, answer=spec.answer, **base)
    step.prompt = task.get("prompt", "")
    step.bullets = list(task.get("bullets", []))
    if task.get("photo"):
        step.photo = f"{photo_url}/{task['photo']}"
    if ttype == "summarize_conversation":
        step.listen = [Line(x["speaker"], x["text"]) for x in task["conversation"]]
    return [step]


def load_round(path: Path) -> Round:
    path = Path(path)
    try:
        data = json.loads((path / "round.json").read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise RoundError(path.name, ["round.json is missing"]) from e
    except json.JSONDecodeError as e:
        raise RoundError(path.name, [f"round.json is not valid JSON: {e}"]) from e
    problems = _check(data, path)
    if problems:
        raise RoundError(path.name, problems)
    steps = [s for t in data["tasks"] for s in _expand(t, f"/rounds/{path.name}/photos")]
    return Round(data["id"], data["title"], path, data.get("photos", {}), steps)


def list_rounds(rounds_dir: Path) -> list[Round]:
    """Every valid round. An invalid round, for example one still being written, is skipped."""
    if not rounds_dir.is_dir():
        return []
    rounds = []
    for p in sorted(rounds_dir.iterdir()):
        if (p / "round.json").is_file():
            try:
                rounds.append(load_round(p))
            except RoundError:
                print(f"Skipped invalid round {p.name}. Run: det-coach check", file=sys.stderr)
    return rounds
