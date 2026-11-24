"""Build practice rounds from the official sample questions.

Usage: python tools/booklet/make_rounds.py .cache/booklet [rounds dir]

Reads the bank that tools/booklet/extract.py wrote and makes the rounds
rounds/official-01 to rounds/official-20. Each round gets every 20th question of each
task type, so it mixes easy and hard questions, and together the rounds use every
question once. The rounds are copyrighted, so .gitignore keeps them out of the
repository. Running the script again replaces them.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROUNDS = 20
BOOKLET = (
    "https://englishtest-static.duolingo.com/media/resources/"
    "GPN%20DET%20Sample%20Questions%20-%20Full.pdf"
)
# Task type -> task id. The order is the order of the test.
ORDER = [
    ("read_select", "select"),
    ("fill_blanks", "blanks"),
    ("read_complete", "complete"),
    ("listen_type", "dictation"),
    ("interactive_reading", "reading"),
    ("interactive_listening", "listening"),
    ("write_photo", "photo"),
    ("interactive_writing", "iw"),
    ("speak_photo", "speak-photo"),
    ("read_then_speak", "read-speak"),
    ("listen_then_speak", "listen-speak"),
    ("writing_sample", "writing-sample"),
    ("speaking_sample", "speaking-sample"),
]
GROUPED = {"read_select", "fill_blanks", "listen_type"}  # one task holds all the items


def share(items: list[dict], r: int) -> list[dict]:
    return items[r::ROUNDS]


def tasks_for(kind: str, tid: str, items: list[dict]) -> list[dict]:
    if not items:
        return []
    if kind == "read_select":
        return [
            {
                "id": tid,
                "type": kind,
                "words": [{"word": i["word"], "real": i["real"]} for i in items],
            }
        ]
    if kind == "fill_blanks":
        return [{"id": tid, "type": kind, "sentences": [i["sentence"] for i in items]}]
    if kind == "listen_type":
        sentences = [
            {"text": i["text"], **({"audio": i["audio"]} if "audio" in i else {})} for i in items
        ]
        return [{"id": tid, "type": kind, "sentences": sentences}]
    out = []
    for k, item in enumerate(items, 1):
        task = {"id": f"{tid}-{k}", "type": kind}
        if kind == "read_complete":
            task |= {"title": item["title"], "passage": item["passage"]}
        elif kind in ("interactive_reading", "interactive_listening"):
            task |= {key: v for key, v in item.items() if key != "n"}
        elif kind in ("write_photo", "speak_photo"):
            task["photo"] = item["photo"]
        elif kind == "interactive_writing":
            follow = item["follow_ups"] or ["Tell me more about your answer."]
            task |= {"prompt": item["prompt"], "follow_up": follow[(item["n"] - 1) % len(follow)]}
        elif kind == "listen_then_speak":
            task["text"] = item["text"]
            if "audio" in item:
                task["audio"] = item["audio"]
        else:
            task["prompt"] = item["prompt"]
        out.append(task)
    return out


def main(bank_dir: Path, rounds_dir: Path) -> None:
    bank = json.loads((bank_dir / "bank.json").read_text(encoding="utf-8"))
    for r in range(ROUNDS):
        rid = f"official-{r + 1:02d}"
        folder = rounds_dir / rid
        if folder.exists():
            shutil.rmtree(folder)
        tasks, photos = [], {}
        for kind, tid in ORDER:
            tasks += tasks_for(kind, tid, share(bank.get(kind, []), r))
        for t in tasks:
            files = [
                t.get("audio"),
                *(s.get("audio") for s in t.get("sentences", []) if isinstance(s, dict)),
            ]
            for name in filter(None, files):
                (folder / "audio").mkdir(parents=True, exist_ok=True)
                shutil.copy(bank_dir / "audio" / name, folder / "audio" / name)
            if "photo" in t:
                (folder / "photos").mkdir(parents=True, exist_ok=True)
                shutil.copy(bank_dir / "photos" / t["photo"], folder / "photos" / t["photo"])
                kind = (
                    "Write About the Photo"
                    if t["type"] == "write_photo"
                    else "Speak About the Photo"
                )
                n = int(t["photo"].rsplit("-", 1)[1].split(".")[0])
                photos[t["photo"]] = {
                    "title": f"{kind}, sample question {n}",
                    "author": "Duolingo",
                    "license": "Official sample question, for personal practice only",
                    "source": BOOKLET,
                }
        data = {
            "id": rid,
            "title": f"Official sample test {r + 1}",
            "tasks": tasks,
            "photos": photos,
            "sources": [BOOKLET],
        }
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "round.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"Wrote {ROUNDS} rounds to {rounds_dir}/official-01 to official-{ROUNDS:02d}.")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) == 3 else "rounds"))
