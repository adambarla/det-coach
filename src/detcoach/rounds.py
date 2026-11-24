"""Load practice rounds from rounds/<id>/round.json and expand them into timed steps.

A task is what a round file lists. A step is one timed screen. Most tasks are one step.
Interactive Writing is two steps and Interactive Speaking is one step per question.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import content
from .model import Line, Step
from .tasks import SECTIONS, TASK_TYPES

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")  # also what the server accepts
VOICES = ("interviewer", "professor", "student", "student2")
PHOTO_FIELDS = ("title", "author", "license", "source")
OFFICIAL = "official-"  # rounds built from the official sample booklet, never committed
DRILL = "drill-"  # practice sets of one task type, made by bank.py in drills/
# test: a full test or a set of tasks to take as it is. pool: questions for drills only.
# drill: a practice set that bank.py made from the questions of other rounds.
KINDS = ("test", "pool", "drill")


def round_dir(root: Path, round_id: str) -> Path:
    """The folder of a round: drills/<id> for a drill, else rounds/<id>."""
    return Path(root) / ("drills" if round_id.startswith(DRILL) else "rounds") / round_id


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
    kind: str = "test"
    # drill: "<task>" or "<task>#<n>" -> the question it came from, "<round>/<task>[#<n>]"
    origin: dict[str, str] = field(default_factory=dict)

    @property
    def minutes(self) -> int:
        return _minutes(self.steps)

    def summary(self) -> dict:
        sections = {}
        for name in SECTIONS:
            steps = [s for s in self.steps if s.section == name]
            if steps:
                sections[name] = {"steps": len(steps), "minutes": max(1, _minutes(steps))}
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "steps": len(self.steps),
            "minutes": self.minutes,
            "sections": sections,
        }

    def public(self) -> dict:
        return {**self.summary(), "steps": [asdict(s) for s in self.steps], "photos": self.photos}


def _minutes(steps: list[Step]) -> int:
    # Prep and answer of every step, and about 15 s per task to read its intro screen.
    tasks = len({s.task for s in steps})
    return round((sum(s.prep + s.answer for s in steps) + 15 * tasks) / 60)


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
    if data.get("kind", "test") not in KINDS:
        problems.append(f"'kind' must be one of {', '.join(KINDS)}")
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
        if ttype == "listen_then_speak":
            _require(task, "text", str, problems, where)
        for audio in _audio_files(task):
            if not FILE_NAME.match(audio):
                problems.append(
                    f"{where}: audio name '{audio}' may use only letters, digits, . _ -"
                )
            elif not (path / "audio" / audio).is_file():
                problems.append(f"{where}: audio file audio/{audio} is missing")
        if ttype in content.CHECKS:
            problems += [f"{where}: {x}" for x in content.CHECKS[ttype](task)]
        if ttype == "interactive_speaking":
            topics = task.get("topics")
            if not isinstance(topics, list) or not topics:
                problems.append(f"{where}: 'topics' needs at least one topic")
            elif any(not t.get("questions") for t in topics):
                problems.append(f"{where}: every topic needs 'questions'")
            elif not all(_question(q) for t in topics for q in t["questions"]):
                problems.append(f"{where}: every question needs text")
    return problems


def _question(q) -> str:
    """An Interactive Speaking question: text, or {"text": ..., "audio": ...}."""
    return q.get("text", "") if isinstance(q, dict) else q


def _audio_files(task: dict) -> list[str]:
    """The recorded audio files that a task names."""
    items = [task, *(x for x in task.get("sentences", []) if isinstance(x, dict))]
    items += [x for x in task.get("conversation", []) if isinstance(x, dict)]
    for topic in task.get("topics", []):
        items += [q for q in topic.get("questions", []) if isinstance(q, dict)]
    names = [x.get("audio") for x in items] + [task.get("scenario_audio")]
    return [x for x in names if isinstance(x, str) and x]


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
                listen=[
                    Line(
                        "interviewer",
                        _question(q),
                        q.get("audio", "") if isinstance(q, dict) else "",
                    )
                ],
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
    if ttype == "listen_then_speak":
        step.listen = [Line("interviewer", task["text"], task.get("audio", ""))]
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
    steps = []
    for task in data["tasks"]:
        for step in _expand(task, f"/rounds/{path.name}/photos"):
            step.section = TASK_TYPES[task["type"]].skill
            steps.append(step)
    return Round(
        data["id"],
        data["title"],
        path,
        data.get("photos", {}),
        steps,
        data.get("kind", "test"),
        data.get("origin", {}),
    )


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


def practice_rounds(rounds_dir: Path) -> list[Round]:
    """The rounds that the home page and the drills use: only the official rounds when
    there are some (tools/booklet makes them), else every round."""
    rounds = list_rounds(rounds_dir)
    official = [r for r in rounds if r.id.startswith(OFFICIAL)]
    return official or rounds


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", content.plain(text).lower()).split())


def _fingerprints(data: dict) -> list[tuple[str, str]]:
    """(kind, text) for every part of a round that a later round must not reuse."""
    out = [("photo", m.get("source", "")) for m in data.get("photos", {}).values()]
    for t in data.get("tasks", []):
        out += [("word", w.get("word", "")) for w in t.get("words", [])]
        out += [("sentence", content._sentence(x)) for x in t.get("sentences", [])]
        for key in ("title", "prompt", "follow_up", "scenario", "passage", "rest"):
            if t.get(key):
                out.append((key.replace("_", " "), t[key]))
        for topic in t.get("topics", []):
            out += [("question", _question(q)) for q in topic.get("questions", [])]
    return [(kind, _norm(text)) for kind, text in out if text]


def repeats(rounds_dir: Path) -> list[str]:
    """Words, sentences, prompts, passages and photos that appear in more than one round.

    Rounds made from the official sample booklet (official-*) are skipped: the booklet
    repeats some of its own prompts, and those rounds stay on this computer."""
    seen: dict[tuple[str, str], str] = {}
    problems = []
    for p in sorted(Path(rounds_dir).iterdir()):
        if p.name.startswith(OFFICIAL):
            continue
        try:
            data = json.loads((p / "round.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for fp in dict.fromkeys(_fingerprints(data)):
            if fp in seen and seen[fp] != p.name:
                problems.append(f"{p.name}: {fp[0]} '{fp[1][:60]}' is already in {seen[fp]}")
            seen.setdefault(fp, p.name)
    return problems
