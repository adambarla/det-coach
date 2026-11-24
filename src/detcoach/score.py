"""Score the reading and listening steps, which have right answers.

The official test marks most of these questions right or wrong and gives partial
credit for Listen and Type, Highlight the Answer and Listen and Complete. It also
adapts the questions to the test taker, so a share of points here does not convert to
a DET score. The results page shows the share and every item.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from .model import Step
from .tasks import GRADED

TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
STOP = {"a", "an", "the", "to", "of", "and", "or", "in", "on", "at", "for", "by", "with", "from"}
STOP |= {"is", "are", "was", "were", "be", "been", "it", "you", "your"}


def _tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower().replace("’", "'"))


def _same(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower()


def _item(prompt: str, given: str, key: str, credit: float) -> dict:
    return {"prompt": prompt, "given": given, "key": key, "credit": round(credit, 2)}


def overlap(given: str, key: str) -> float:
    """Token F1 between a highlight and the answer: 1 when exact, partial when close."""
    g, k = _tokens(given), _tokens(key)
    if not g or not k:
        return 0.0
    common = sum(min(g.count(t), k.count(t)) for t in set(k))
    if not common:
        return 0.0
    precision, recall = common / len(g), common / len(k)
    return 2 * precision * recall / (precision + recall)


def idea_credit(given: str, key: str) -> float:
    """Listen and Complete accepts your own words: the share of key words in the answer.

    A word counts when a given word is the same or a near spelling (small errors are
    not marked down).
    """
    words = [t for t in _tokens(key) if t not in STOP] or _tokens(key)
    have = _tokens(given)
    hits = sum(any(SequenceMatcher(None, w, h).ratio() >= 0.8 for h in have) for w in words)
    return hits / len(words) if words else 0.0


def dictation_credit(given: str, key: str) -> float:
    """Listen and Type: closeness to the sentence, with spelling and punctuation."""
    norm = lambda s: " ".join(s.lower().replace("’", "'").split())  # noqa: E731
    return SequenceMatcher(None, norm(given), norm(key)).ratio() if given.strip() else 0.0


def _choice(prompt: str, given, key: str) -> dict:
    given = given or ""
    return _item(prompt, given, key, float(_same(given, key)))


def score_step(step: Step, raw: str) -> dict:
    """Score one saved answer. Returns {"credit", "points", "items"}."""
    try:
        ans = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        ans = {}
    if not isinstance(ans, dict):
        ans = {}
    k = step.key
    items: list[dict] = []
    if step.type == "read_select":
        choice = ans.get("real")
        right = choice is not None and bool(choice) == k["real"]
        label = {True: "Yes", False: "No", None: "No answer"}[choice]
        items.append(_item(step.data["word"], label, "Yes" if k["real"] else "No", float(right)))
    elif step.type in ("fill_blanks", "read_complete"):
        typed = ans.get("missing") or []
        shown = [s["shown"] for s in step.data["segments"] if isinstance(s, dict)]
        for i, (prefix, missing) in enumerate(zip(shown, k["missing"], strict=True)):
            got = typed[i] if i < len(typed) and isinstance(typed[i], str) else ""
            right = float(_same(got, missing))
            items.append(_item(prefix + "…", prefix + got, prefix + missing, right))
    elif step.type == "listen_type":
        text = ans.get("text") or ""
        items.append(_item("Sentence", text, k["text"], dictation_credit(text, k["text"])))
    elif step.type == "interactive_reading":
        chosen = ans.get("choices") or []
        for i, right in enumerate(k["choices"]):
            got = chosen[i] if i < len(chosen) else ""
            items.append(_choice(f"Complete the Sentences, word {i + 1}", got, right))
        items.append(_choice("Complete the Passage", ans.get("missing"), k["missing"]))
        marks = ans.get("highlight") or []
        for i, (q, right) in enumerate(zip(step.data["highlight"], k["highlight"], strict=True)):
            got = marks[i] if i < len(marks) and isinstance(marks[i], str) else ""
            items.append(_item(f"Highlight: {q}", got, right, overlap(got, right)))
        items.append(_choice("Identify the Idea", ans.get("idea"), k["idea"]))
        items.append(_choice("Title the Passage", ans.get("title"), k["title"]))
    elif step.type == "interactive_listening":
        typed = ans.get("complete") or []
        for i, ((before, after), right) in enumerate(
            zip(step.data["complete"], k["complete"], strict=True)
        ):
            got = typed[i] if i < len(typed) and isinstance(typed[i], str) else ""
            items.append(_item(f"{before}___{after}", got, right, idea_credit(got, right)))
        picked = ans.get("turns") or []
        for i, right in enumerate(k["turns"]):
            got = picked[i] if i < len(picked) else ""
            items.append(_choice(f"Listen and Respond, reply {i + 1}", got, right))
    else:
        raise ValueError(f"{step.type} is not scored by det-coach")
    credit = sum(x["credit"] for x in items)
    return {"credit": round(credit, 2), "points": len(items), "items": items}


def summary(scores: dict[str, dict], steps: dict[str, Step]) -> dict[str, dict]:
    """Points per skill, e.g. {"reading": {"credit": 31.5, "points": 40, "share": 0.79}}."""
    out: dict[str, dict] = {}
    for sid, s in scores.items():
        d = out.setdefault(steps[sid].skill, {"credit": 0.0, "points": 0})
        d["credit"] += s["credit"]
        d["points"] += s["points"]
    for d in out.values():
        d["credit"] = round(d["credit"], 2)
        d["share"] = round(d["credit"] / d["points"], 2) if d["points"] else 0.0
    return out


def score_attempt(rnd, attempt_dir: Path, manifest: dict) -> dict[str, dict]:
    """Scores of every submitted reading and listening step of an attempt."""
    out = {}
    for step in rnd.steps:
        saved = manifest["steps"].get(step.id)
        if step.skill in GRADED or not saved:
            continue
        out[step.id] = score_step(step, (attempt_dir / saved["file"]).read_text(encoding="utf-8"))
    return out
