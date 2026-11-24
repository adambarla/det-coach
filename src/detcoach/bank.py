"""Practice one task type at a time: drills made from the questions of every round.

An item is one question that a drill can use: a word (Read and Select), a sentence
(Fill in the Blanks, Listen and Type), a topic (Interactive Speaking) or a whole task.
Its key is "<round>/<task>" or "<round>/<task>#<n>", with n from 1.

Full tests stay fresh. A drill uses a question of a test round only after you answered
it in that test. Pool rounds ("kind": "pool") hold questions for drills only. When there
are official rounds (tools/booklet), the drills and the progress use only those.
"""

from __future__ import annotations

import json
import random
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import feedback, score
from .attempts import Attempts
from .model import Step
from .rounds import DRILL, Round, RoundError, load_round, practice_rounds, round_dir
from .tasks import DRILLS, GRADED, TASK_TYPES

# Task types whose task holds a list of questions, and the key of that list.
GROUPED = {
    "read_select": "words",
    "fill_blanks": "sentences",
    "listen_type": "sentences",
    "interactive_speaking": "topics",
}
# The task id in a drill, and how many questions one drill has (about the real test).
SHORT = {
    "read_select": ("select", 16),
    "fill_blanks": ("blanks", 7),
    "read_complete": ("complete", 2),
    "listen_type": ("dictation", 7),
    "interactive_reading": ("reading", 1),
    "interactive_listening": ("listening", 1),
    "write_photo": ("photo", 3),
    "interactive_writing": ("iw", 1),
    "summarize_conversation": ("summary", 1),
    "writing_sample": ("writing-sample", 1),
    "speak_photo": ("speak-photo", 2),
    "read_then_speak": ("read-speak", 2),
    "interactive_speaking": ("talk", 2),
    "speaking_sample": ("speaking-sample", 1),
    "listen_then_speak": ("listen-speak", 2),
}
# The summary drill also uses Interactive Listening conversations, without the questions.
SOURCES = {"summarize_conversation": ("summarize_conversation", "interactive_listening")}
RECENT_SCORED = 40  # reading and listening: the share of points of the last 40 points
RECENT_GRADED = 6  # writing and speaking: the mean band of the last 6 graded answers


@dataclass
class Item:
    key: str
    type: str
    round: Round
    task: dict
    part: object = None  # the word, sentence or topic of a grouped task


def _tasks(rnd: Round) -> list[dict]:
    return json.loads((rnd.path / "round.json").read_text(encoding="utf-8"))["tasks"]


def items(rounds: list[Round]) -> list[Item]:
    """Every question of the test and pool rounds."""
    out = []
    for rnd in rounds:
        if rnd.kind == "drill":
            continue
        for task in _tasks(rnd):
            key, ttype = f"{rnd.id}/{task['id']}", task["type"]
            if ttype in GROUPED:
                out += [
                    Item(f"{key}#{n}", ttype, rnd, task, part)
                    for n, part in enumerate(task[GROUPED[ttype]], 1)
                ]
            else:
                out.append(Item(key, ttype, rnd, task))
    return out


def step_item(rnd: Round, step: Step) -> str:
    """The key of the question that a step asks."""
    local = step.task
    if step.type in GROUPED and step.type != "interactive_speaking":
        local += "#" + step.id.rsplit("-", 1)[1]
    elif step.type == "interactive_speaking":
        n = int(step.id.rsplit("-", 1)[1])
        topics = next(t for t in _tasks(rnd) if t["id"] == step.task)["topics"]
        for i, topic in enumerate(topics, 1):
            if n <= len(topic["questions"]):
                local += f"#{i}"
                break
            n -= len(topic["questions"])
    return rnd.origin.get(local, f"{rnd.id}/{local}")


@dataclass
class Answer:
    key: str  # the question
    type: str  # the task type of the step (an Interactive Listening summary is its own type)
    saved: str
    credit: float | None = None  # reading and listening
    points: int = 0
    band: float | None = None  # writing and speaking, once graded: the middle of the band


def history(root: Path) -> list[Answer]:
    """Every submitted answer of every attempt, oldest first."""
    attempts = Attempts(Path(root) / "attempts")
    out, cache = [], {}
    for a in attempts.all():
        rid = a["round"]
        if rid not in cache:
            try:
                cache[rid] = load_round(round_dir(root, rid))
            except (RoundError, FileNotFoundError):
                cache[rid] = None
        rnd = cache[rid]
        if rnd is None:
            continue
        base = attempts.path(a["id"])
        manifest = attempts.manifest(a["id"])
        fb = feedback.load_feedback(base)
        if fb is not None and feedback.check(fb, rnd, manifest):
            fb = None
        for step in rnd.steps:
            saved = manifest["steps"].get(step.id)
            if not saved:
                continue
            ans = Answer(step_item(rnd, step), step.type, saved["saved"])
            if step.skill in GRADED:
                band = ((fb or {}).get("steps") or {}).get(step.id, {}).get("band")
                ans.band = sum(band) / 2 if band else None
            else:
                raw = (base / saved["file"]).read_text(encoding="utf-8")
                s = score.score_step(step, raw)
                ans.credit, ans.points = s["credit"], s["points"]
            out.append(ans)
    return sorted(out, key=lambda x: x.saved)


def progress(root: Path) -> list[dict]:
    """For each task type: questions done and left, and how well the recent answers went."""
    rounds = practice_rounds(Path(root) / "rounds")
    pool = items(rounds)
    ids = {r.id for r in rounds}
    answers = [a for a in history(root) if a.key.split("/", 1)[0] in ids]
    seen = {a.key for a in answers}
    out = []
    for ttype in DRILLS:
        spec = TASK_TYPES[ttype]
        mine = [a for a in answers if a.type == ttype]
        qs = [i for i in pool if i.type in SOURCES.get(ttype, (ttype,))]
        row = {
            "type": ttype,
            "name": spec.name,
            "skill": spec.skill,
            "section": spec.skill,
            "done": len({a.key for a in mine}),
            "fresh": sum(i.key not in seen for i in qs if i.round.kind == "pool"),
            "held": sum(i.key not in seen for i in qs if i.round.kind == "test"),
            "answers": len(mine),
            "last": mine[-1].saved if mine else None,
        }
        if spec.skill in GRADED:
            graded = [a.band for a in mine if a.band is not None][-RECENT_GRADED:]
            row["band"] = round(sum(graded) / len(graded)) if graded else None
            row["graded"] = len(graded)
            row["ungraded"] = sum(a.band is None for a in mine)
        else:
            recent, points = [], 0
            for a in reversed(mine):
                if points >= RECENT_SCORED:
                    break
                recent.append(a)
                points += a.points
            credit = sum(a.credit for a in recent)
            row["share"] = round(credit / points, 2) if points else None
        out.append(row)
    return out


def _pick(candidates: list[Item], last_seen: dict[str, str], n: int) -> list[Item]:
    """Questions not seen yet first, in random order, then the ones seen longest ago."""
    fresh = [i for i in candidates if i.key not in last_seen]
    random.shuffle(fresh)
    old = sorted((i for i in candidates if i.key in last_seen), key=lambda i: last_seen[i.key])
    return (fresh + old)[:n]


def _copy(src: Path, dst_dir: Path, name: str) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst_dir / name)


def prune(root: Path, hours: int = 12) -> None:
    """Remove drills that no attempt uses, for example a set that was never begun."""
    used = {a["round"] for a in Attempts(root / "attempts").all()}
    limit = datetime.now().timestamp() - hours * 3600
    for p in (root / "drills").glob(f"{DRILL}*"):
        if p.name not in used and p.stat().st_mtime < limit:
            shutil.rmtree(p)


def make_drill(root: Path, ttype: str) -> str:
    """Write drills/<id>/round.json with fresh questions of one task type. Returns the id."""
    if ttype not in DRILLS:
        raise ValueError(f"no drill for {ttype}")
    root = Path(root)
    last_seen: dict[str, str] = {}
    for a in history(root):
        last_seen[a.key] = a.saved
    prune(root)
    rounds = practice_rounds(root / "rounds")
    candidates = [
        i
        for i in items(rounds)
        if i.type in SOURCES.get(ttype, (ttype,)) and (i.round.kind == "pool" or i.key in last_seen)
    ]
    tid, size = SHORT[ttype]
    chosen = _pick(candidates, last_seen, size)
    if not chosen:
        raise LookupError(f"no questions for {TASK_TYPES[ttype].name} yet")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rid = f"{DRILL}{tid}-{stamp}"
    folder = root / "drills" / rid
    n = 1
    while folder.exists():
        n += 1
        folder = root / "drills" / f"{DRILL}{tid}-{stamp}-{n}"
    rid = folder.name
    folder.mkdir(parents=True)
    photos, origin, tasks = {}, {}, []

    def audio(item: Item, obj):
        """A copy of a task or part whose recordings are copied into the drill."""
        if isinstance(obj, list):
            return [audio(item, x) for x in obj]
        if not isinstance(obj, dict):
            return obj
        out = {}
        for k, v in obj.items():
            if k in ("audio", "scenario_audio") and isinstance(v, str) and v:
                out[k] = f"{item.round.id}-{v}"
                _copy(item.round.path / "audio" / v, folder / "audio", out[k])
            else:
                out[k] = audio(item, v)
        return out

    if ttype in GROUPED:
        parts = []
        for n, item in enumerate(chosen, 1):
            parts.append(audio(item, item.part))
            origin[f"{tid}#{n}"] = item.key
        tasks.append({"id": tid, "type": ttype, GROUPED[ttype]: parts})
    else:
        for n, item in enumerate(chosen, 1):
            task = {**audio(item, item.task), "id": f"{tid}-{n}"}
            if ttype == "summarize_conversation" and item.type == "interactive_listening":
                task = summary_task(item.task, task["id"])
            if task.get("photo"):
                new = f"{item.round.id}-{task['photo']}"
                _copy(item.round.path / "photos" / task["photo"], folder / "photos", new)
                photos[new] = item.round.photos[task["photo"]]
                task["photo"] = new
            tasks.append(task)
            origin[task["id"]] = item.key
    data = {
        "id": rid,
        "title": f"{TASK_TYPES[ttype].name} practice",
        "kind": "drill",
        "tasks": tasks,
        "photos": photos,
        "origin": origin,
    }
    (folder / "round.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    try:
        load_round(folder)
    except RoundError:
        shutil.rmtree(folder)
        raise
    return rid


def summary_task(il: dict, tid: str) -> dict:
    """Summarize the Conversation from an Interactive Listening task: the conversation
    with the right replies, without the questions."""
    partner = il["partner"]
    you = "student2" if partner == "student" else "student"
    lines = [
        {"speaker": partner, "text": t["partner"]}
        if "partner" in t
        else {"speaker": you, "text": t["you"]["answer"]}
        for t in il["conversation"]
    ]
    return {"id": tid, "type": "summarize_conversation", "conversation": lines}
