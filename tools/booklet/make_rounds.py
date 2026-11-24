"""Build practice rounds from the official sample questions.

Usage: python tools/booklet/make_rounds.py <bank dir>...
Example: python tools/booklet/make_rounds.py .cache/booklet .cache/vol4 .cache/vol5

Each bank dir holds the bank.json, photos/ and audio/ that an extractor wrote
(extract.py for the 2025 booklet, extract_2026.py for the 2026 volumes). This makes:

- rounds/official-test-01 to official-test-04: full tests with as many questions of each
  type as the real test (Questions Guide 2026). They take questions only from the banks
  in the current format (the ones with Interactive Speaking), spread over each booklet,
  so a test mixes easy and hard questions. Drills do not use these questions until you
  take the test.
- rounds/official-<bank>: every other question of a bank, for drills only ("kind": "pool").

Task types that the current test no longer uses (Read Aloud, Listen, Then Speak) are
left out. The rounds are copyrighted, so .gitignore keeps them out of the repository.
Running the script again replaces them, except rounds that an attempt uses.
"""

from __future__ import annotations

import json
import shutil
import sys
from itertools import zip_longest
from pathlib import Path

TESTS = 4
RESOURCES = "https://englishtest-static.duolingo.com/media/resources/"
SOURCES = {
    "booklet": RESOURCES + "GPN%20DET%20Sample%20Questions%20-%20Full.pdf",
    "vol4": RESOURCES + "DET%20Practice%20Questions%20Volume%204.pdf",
    "vol5": RESOURCES + "Practice%20Questions%20-%20Volume%205.pdf",
}
TITLES = {
    "booklet": "Official sample questions (2025)",
    "vol4": "Official practice questions, Volume 4 (2026)",
    "vol5": "Official practice questions, Volume 5 (2026)",
}
# Task type -> (task id, questions in one full test). The order is the order of the test.
ORDER = {
    "read_select": ("select", 16),
    "fill_blanks": ("blanks", 7),
    "read_complete": ("complete", 3),
    "listen_type": ("dictation", 7),
    "interactive_reading": ("reading", 2),
    "interactive_listening": ("listening", 2),
    "write_photo": ("photo", 3),
    "interactive_writing": ("iw", 1),
    "speak_photo": ("speak-photo", 1),
    "read_then_speak": ("read-speak", 1),
    "interactive_speaking": ("talk", 1),
    "writing_sample": ("writing-sample", 1),
    "speaking_sample": ("speaking-sample", 1),
}
FILES: dict[str, Path] = {}  # the name of a photo or recording in a round -> its file


def load(bank_dir: Path) -> tuple[str, dict]:
    """A bank, with each photo and recording renamed '<bank>-<name>' so that names of
    different banks never clash in one round."""
    label = bank_dir.name
    bank = json.loads((bank_dir / "bank.json").read_text(encoding="utf-8"))

    def rename(obj):
        if isinstance(obj, list):
            return [rename(x) for x in obj]
        if not isinstance(obj, dict):
            return obj
        out = {}
        for k, v in obj.items():
            if k in ("audio", "scenario_audio", "photo") and isinstance(v, str) and v:
                out[k] = f"{label}-{v}"
                FILES[out[k]] = bank_dir / ("photos" if k == "photo" else "audio") / v
            else:
                out[k] = rename(v)
        return out

    data = {k: [{**rename(i), "bank": label} for i in v] for k, v in bank.items() if k in ORDER}
    return label, data


def split(items: list[dict], count: int) -> tuple[list[list[dict]], list[dict]]:
    """The questions of each test, spread over the booklets, and the rest for the pools."""
    step = len(items) // count
    tests = [[items[t + j * step] for j in range(count)] for t in range(min(TESTS, step))]
    used = {id(x) for test in tests for x in test}
    return tests, [x for x in items if id(x) not in used]


def task(kind: str, tid: str, item: dict) -> dict:
    out = {"id": tid, "type": kind}
    if kind == "read_complete":
        out |= {"title": item["title"], "passage": item["passage"]}
    elif kind in ("interactive_reading", "interactive_listening"):
        out |= {k: v for k, v in item.items() if k not in ("n", "bank")}
    elif kind in ("write_photo", "speak_photo"):
        out["photo"] = item["photo"]
    elif kind == "interactive_writing":
        follow = item["follow_ups"] or ["Tell me more about your answer."]
        out |= {"prompt": item["prompt"], "follow_up": follow[(item["n"] - 1) % len(follow)]}
    elif kind == "interactive_speaking":
        out["topics"] = item["topics"]
    else:
        out["prompt"] = item["prompt"]
        if item.get("bullets"):
            out["bullets"] = item["bullets"]
    return out


def tasks_for(kind: str, items: list[dict], stable: bool) -> list[dict]:
    """The tasks of some questions of one type. stable: name each task by its number in
    the booklet (pools, so that a question keeps its id when the rounds are made again)."""
    tid = ORDER[kind][0]
    if not items:
        return []
    if kind == "read_select":
        words = [{"word": i["word"], "real": i["real"]} for i in items]
        return [{"id": tid, "type": kind, "words": words}]
    if kind == "fill_blanks":
        return [{"id": tid, "type": kind, "sentences": [i["sentence"] for i in items]}]
    if kind == "listen_type":
        sentences = [
            {"text": i["text"], "audio": i["audio"]} if i.get("audio") else i["text"] for i in items
        ]
        return [{"id": tid, "type": kind, "sentences": sentences}]
    return [
        task(kind, f"{tid}-{item['n'] if stable else k}", item) for k, item in enumerate(items, 1)
    ]


def write_round(folder: Path, data: dict, sources: list[str]) -> None:
    """Write round.json, with the photos and recordings that its tasks use."""
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    photos = {}
    text = json.dumps(data["tasks"])
    for name, src in FILES.items():
        if f'"{name}"' not in text:
            continue
        sub = src.parent.name
        (folder / sub).mkdir(exist_ok=True)
        shutil.copy(src, folder / sub / name)
        if sub == "photos":
            label = name.split("-", 1)[0]
            kind = "Write About the Photo" if "write" in name else "Speak About the Photo"
            photos[name] = {
                "title": f"{kind}, {TITLES.get(label, label)}",
                "author": "Duolingo",
                "license": "Official sample question, for personal practice only",
                "source": SOURCES.get(label, RESOURCES),
            }
    data = {**data, "photos": photos, "sources": sources}
    (folder / "round.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def main(bank_dirs: list[Path], rounds_dir: Path) -> None:
    banks = dict(load(d) for d in bank_dirs)
    current = [b for b, data in banks.items() if data.get("interactive_speaking")] or list(banks)
    used = {
        json.loads(p.read_text()).get("round")
        for p in (rounds_dir.parent / "attempts").glob("*/attempt.json")
    }
    tests: list[list[dict]] = [[] for _ in range(TESTS)]
    pools: dict[str, list[dict]] = {b: [] for b in banks}
    for kind, (_, count) in ORDER.items():
        # Alternate the banks, so that each test takes questions from all of them.
        mixed = [
            i for group in zip_longest(*(banks[b].get(kind, []) for b in current)) for i in group
        ]
        per_test, rest = split([i for i in mixed if i], count)
        for t, items in enumerate(per_test):
            tests[t] += tasks_for(kind, items, stable=False)
        for b, data in banks.items():
            mine = [i for i in rest if i["bank"] == b] if b in current else data.get(kind, [])
            pools[b] += tasks_for(kind, mine, stable=True)
    for old in rounds_dir.glob("official-*"):
        if old.name in used:
            print(f"Kept {old.name}: an attempt uses it.")
        else:
            shutil.rmtree(old)
    sources = [SOURCES.get(b, RESOURCES) for b in current]
    for t, tasks in enumerate(tests, 1):
        rid = f"official-test-{t:02d}"
        if tasks and rid not in used:
            title = f"Official sample test {t}"
            write_round(rounds_dir / rid, {"id": rid, "title": title, "tasks": tasks}, sources)
    for b, tasks in pools.items():
        rid = f"official-{b}"
        data = {"id": rid, "title": TITLES.get(b, b), "kind": "pool", "tasks": tasks}
        if tasks and rid not in used:
            write_round(rounds_dir / rid, data, [SOURCES.get(b, RESOURCES)])
    print(f"Wrote {TESTS} full tests from {', '.join(current)} and pools of {', '.join(banks)}.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main([Path(p) for p in sys.argv[1:]], Path("rounds"))
