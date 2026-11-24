"""Reading and listening tasks: check their content in round.json and expand them into steps.

These tasks have right answers, so det-coach scores them itself (see score.py). The
round author marks the answers in the text:

- `{word}` is a word with its second half missing. `{sh|own}` sets the split by hand.
- `{right|wrong|wrong}` in Interactive Reading is a word to choose from a list.
"""

from __future__ import annotations

import random
import re

from .model import Line, Step
from .tasks import TaskType

BLANK = re.compile(r"\{([^{}]+)\}")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
NARRATOR = "interviewer"


def segments(text: str, choices: bool = False, seed: str = "") -> tuple[list, list[str]]:
    """Split text at its {blanks}. Returns (segments for the screen, the answers).

    A segment is a string, or a blank: {"shown", "len"} for a word to finish, or
    {"options"} for a word to choose.
    """
    out: list = []
    answers: list[str] = []
    pos = 0
    for n, m in enumerate(BLANK.finditer(text)):
        out.append(text[pos : m.start()])
        parts = m.group(1).split("|")
        if choices:
            options = list(parts)
            random.Random(f"{seed}-{n}").shuffle(options)
            out.append({"options": options})
            answers.append(parts[0])
        else:
            word = "".join(parts)
            shown = parts[0] if len(parts) == 2 else word[: len(word) // 2]
            out.append({"shown": shown, "len": len(word) - len(shown)})
            answers.append(word[len(shown) :])
        pos = m.end()
    out.append(text[pos:])
    return [s for s in out if s != ""], answers


def plain(text: str) -> str:
    """The text with every blank filled with its answer."""
    return BLANK.sub(lambda m: m.group(1).split("|")[0] if "|" in m.group(1) else m.group(1), text)


def _filled(text: str) -> str:
    """Like plain(), but {sh|own} becomes 'shown', for words to finish."""
    return BLANK.sub(lambda m: m.group(1).replace("|", ""), text)


def _options(spec: dict, seed: str) -> list[str]:
    options = [spec["answer"], *spec["wrong"]]
    random.Random(seed).shuffle(options)
    return options


def _choice_problems(spec, name: str) -> list[str]:
    ok = (
        isinstance(spec, dict)
        and isinstance(spec.get("answer"), str)
        and spec["answer"]
        and isinstance(spec.get("wrong"), list)
        and len(spec["wrong"]) >= 2
        and all(isinstance(w, str) and w for w in spec["wrong"])
    )
    return [] if ok else [f"'{name}' needs an 'answer' and at least 2 'wrong' options"]


def _strings(task: dict, key: str) -> list[str] | None:
    v = task.get(key)
    return v if isinstance(v, list) and v and all(isinstance(x, str) and x for x in v) else None


# ---------- checks: each returns a list of problems ----------


def check_read_select(task: dict) -> list[str]:
    words = task.get("words")
    if not isinstance(words, list) or not words:
        return ['needs \'words\', a list of {"word", "real"}']
    ok = (isinstance(w, dict) and w.get("word") and isinstance(w.get("real"), bool) for w in words)
    if not all(ok):
        return ["each word needs 'word' and 'real' (true or false)"]
    if {w["real"] for w in words} != {True, False}:
        return ["'words' needs both real and invented words"]
    return []


def check_fill_blanks(task: dict) -> list[str]:
    sentences = _strings(task, "sentences")
    if sentences is None:
        return ["needs 'sentences', a list of strings"]
    return [
        f"sentence {i} needs exactly one {{word}}"
        for i, s in enumerate(sentences, 1)
        if len(BLANK.findall(s)) != 1
    ]


def check_read_complete(task: dict) -> list[str]:
    problems = [] if task.get("title") else ["needs a 'title'"]
    text = task.get("passage")
    if not isinstance(text, str) or not text:
        return [*problems, "needs a 'passage'"]
    sentences = SENTENCE_END.split(text.strip())
    if len(BLANK.findall(text)) < 5:
        problems.append("'passage' needs at least 5 {words}")
    if len(sentences) < 3 or BLANK.search(sentences[0]) or BLANK.search(sentences[-1]):
        problems.append("the first and last sentences of 'passage' must have no blanks")
    if re.search(r"\}\s*\{", text):
        problems.append("two {words} must not be next to each other")
    return problems


def check_listen_type(task: dict) -> list[str]:
    return [] if _strings(task, "sentences") else ["needs 'sentences', a list of strings"]


def check_interactive_reading(task: dict) -> list[str]:
    p = []
    passage = task.get("passage")
    if not isinstance(passage, str) or not 3 <= len(BLANK.findall(passage)) <= 10:
        p.append("'passage' needs 3 to 10 {right|wrong|wrong} choices")
    elif any(len(m.split("|")) < 3 for m in BLANK.findall(passage)):
        p.append("each choice in 'passage' needs the right word and at least 2 wrong ones")
    if not isinstance(task.get("rest"), str) or not task.get("rest"):
        p.append("needs 'rest', the second half of the text")
    for name in ("missing_sentence", "main_idea", "best_title"):
        p += _choice_problems(task.get(name), name)
    highlight = task.get("highlight")
    if not isinstance(highlight, list) or len(highlight) != 2:
        return [*p, "'highlight' needs 2 questions with 'question' and 'answer'"]
    if p:
        return p
    full = full_text(task)
    for i, h in enumerate(highlight, 1):
        if not isinstance(h, dict) or not h.get("question") or not h.get("answer"):
            p.append(f"highlight {i} needs 'question' and 'answer'")
        elif h["answer"] not in full:
            p.append(f"highlight {i}: the answer must be words copied from the text")
    return p


def check_interactive_listening(task: dict) -> list[str]:
    p = []
    if task.get("partner") not in ("professor", "student", "student2"):
        p.append("'partner' must be professor, student or student2")
    if not isinstance(task.get("scenario"), str) or not task.get("scenario"):
        p.append("needs a 'scenario'")
    complete = task.get("complete")
    if not isinstance(complete, list) or not 3 <= len(complete) <= 4:
        p.append("'complete' needs 3 or 4 sentences")
    elif not all(
        isinstance(c, dict) and c.get("sentence", "").count("___") == 1 and c.get("answer")
        for c in complete
    ):
        p.append("each 'complete' item needs a 'sentence' with one ___ and an 'answer'")
    turns = task.get("conversation")
    if not isinstance(turns, list) or not turns:
        return [*p, "needs a 'conversation'"]
    yours = [t["you"] for t in turns if isinstance(t, dict) and "you" in t]
    if not 5 <= len(yours) <= 6:
        p.append("'conversation' needs 5 or 6 turns with 'you'")
    for i, turn in enumerate(turns, 1):
        if not isinstance(turn, dict) or len(turn) != 1 or not ({"you", "partner"} >= turn.keys()):
            p.append(f'conversation turn {i} must be {{"partner": text}} or {{"you": choice}}')
        elif "you" in turn:
            p += [f"conversation turn {i}: {x}" for x in _choice_problems(turn["you"], "you")]
        elif not isinstance(turn["partner"], str) or not turn["partner"]:
            p.append(f"conversation turn {i}: 'partner' needs text")
    return p


# ---------- expansion into steps ----------


def full_text(task: dict) -> str:
    return " ".join(
        [plain(task["passage"]).strip(), task["missing_sentence"]["answer"], task["rest"].strip()]
    )


def expand_read_select(task: dict, spec: TaskType, base: dict) -> list[Step]:
    words = task["words"]
    return [
        Step(
            id=f"{task['id']}-{n}",
            prep=0,
            answer=spec.answer,
            part=f"Word {n} of {len(words)}",
            data={"word": w["word"]},
            key={"real": w["real"]},
            **base,
        )
        for n, w in enumerate(words, 1)
    ]


def expand_fill_blanks(task: dict, spec: TaskType, base: dict) -> list[Step]:
    steps = []
    for n, sentence in enumerate(task["sentences"], 1):
        segs, answers = segments(sentence)
        steps.append(
            Step(
                id=f"{task['id']}-{n}",
                prep=0,
                answer=spec.answer,
                part=f"Sentence {n} of {len(task['sentences'])}",
                data={"segments": segs},
                key={"missing": answers, "text": _filled(sentence)},
                **base,
            )
        )
    return steps


def expand_read_complete(task: dict, spec: TaskType, base: dict) -> list[Step]:
    segs, answers = segments(task["passage"])
    data = {"title": task["title"], "segments": segs}
    key = {"missing": answers, "text": _filled(task["passage"])}
    return [Step(id=task["id"], prep=0, answer=spec.answer, data=data, key=key, **base)]


def expand_listen_type(task: dict, spec: TaskType, base: dict) -> list[Step]:
    sentences = task["sentences"]
    return [
        Step(
            id=f"{task['id']}-{n}",
            prep=0,
            answer=spec.answer,
            part=f"Sentence {n} of {len(sentences)}",
            listen=[Line(NARRATOR, s)],
            key={"text": s},
            **base,
        )
        for n, s in enumerate(sentences, 1)
    ]


def expand_interactive_reading(task: dict, spec: TaskType, base: dict) -> list[Step]:
    tid = task["id"]
    segs, answers = segments(task["passage"], choices=True, seed=tid)
    data = {
        "passage": segs,
        "missing_options": _options(task["missing_sentence"], f"{tid}-missing"),
        "rest": task["rest"],
        "highlight": [h["question"] for h in task["highlight"]],
        "idea_options": _options(task["main_idea"], f"{tid}-idea"),
        "title_options": _options(task["best_title"], f"{tid}-title"),
    }
    key = {
        "choices": answers,
        "missing": task["missing_sentence"]["answer"],
        "full_text": full_text(task),
        "highlight": [h["answer"] for h in task["highlight"]],
        "idea": task["main_idea"]["answer"],
        "title": task["best_title"]["answer"],
    }
    return [Step(id=tid, prep=0, answer=spec.answer, data=data, key=key, **base)]


def expand_interactive_listening(task: dict, spec: TaskType, base: dict) -> list[Step]:
    """Listen and Complete with Listen and Respond (one shared timer), then the summary."""
    tid, partner = task["id"], task["partner"]
    listen = [Line(NARRATOR, task["scenario"])]
    turns, answers, lines = [], [], []
    for n, turn in enumerate(task["conversation"]):
        if "partner" in turn:
            turns.append({"clip": len(listen)})
            listen.append(Line(partner, turn["partner"]))
            lines.append(Line(partner, turn["partner"]))
        else:
            turns.append({"options": _options(turn["you"], f"{tid}-turn-{n}")})
            answers.append(turn["you"]["answer"])
            lines.append(Line("you", turn["you"]["answer"]))
    complete = [c["sentence"].split("___") for c in task["complete"]]
    main = Step(
        id=tid,
        prep=0,
        answer=spec.answer,
        part="Listen and Complete, Listen and Respond",
        listen=listen,
        data={"complete": complete, "turns": turns, "partner": partner},
        key={"complete": [c["answer"] for c in task["complete"]], "turns": answers},
        **base,
    )
    summary = Step(
        id=f"{tid}-summary",
        task=tid,
        type="summarize_conversation",
        name="Summarize the Conversation",
        skill="writing",
        prep=0,
        answer=spec.follow_up_answer,
        part="Interactive Listening",
        listen=[Line(NARRATOR, task["scenario"]), *lines],
        after=tid,
    )
    return [main, summary]


CHECKS = {
    "read_select": check_read_select,
    "fill_blanks": check_fill_blanks,
    "read_complete": check_read_complete,
    "listen_type": check_listen_type,
    "interactive_reading": check_interactive_reading,
    "interactive_listening": check_interactive_listening,
}
EXPANDERS = {
    "read_select": expand_read_select,
    "fill_blanks": expand_fill_blanks,
    "read_complete": expand_read_complete,
    "listen_type": expand_listen_type,
    "interactive_reading": expand_interactive_reading,
    "interactive_listening": expand_interactive_listening,
}
