"""Extract the scored sample answers of the DET Scoring Guide (2026), section 6.

Usage: python tools/calibration/extract.py <Scoring Guide PDF> <output dir>

Writes blind.md (the answers without scores or comments, for the graders) and
key.json (the official subscores). Needs `pdftotext` from poppler. The samples are
copyrighted, so the output belongs in .cache/, never in the repository.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

FOOTER = re.compile(r"©|^\s*Scoring Guide\s*$|^\s*duolingo english test\s*$|^\s*\d+\s*$")
HELD_OUT = 2  # the second sample of each task is held out: the rubric anchors skip it


def extract(pdf: Path) -> list[dict]:
    text = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    start = [m.start() for m in re.finditer(r"(?m)^\s*6\. Sample Answers\s*$", text)][-1]
    samples, cur, task, mode = [], None, None, None
    for line in text[start:].splitlines():
        if m := re.match(r"^6\.(\d)[\s\u2000-\u200f]+(\S.*)$", line.strip()):
            task, mode = m.group(2).strip(), None
            continue
        if task is None or FOOTER.search(line):
            continue
        if (q := re.match(r"^Question (\d+)\s*$", line.strip())) and mode != "body":
            cur = {"task": task, "n": int(q.group(1)), "text": []}
            samples.append(cur)
            mode = "body"
            continue
        if s := re.match(r"This test taker scored (\d+) for (Writing|Speaking)", line.strip()):
            cur.update(score=int(s.group(1)), skill=s.group(2))
            mode = "comments"
            continue
        if mode == "body":
            cur["text"].append(line.strip())
    for i, x in enumerate(samples, 1):
        x["id"] = f"S{i:02d}"
        x["held_out"] = x["n"] == HELD_OUT
        x["text"] = re.sub(r"\n{3,}", "\n\n", "\n".join(x["text"]).strip())
    return [x for x in samples if "score" in x]


def main() -> None:
    pdf, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    samples = extract(pdf)
    with open(out / "blind.md", "w", encoding="utf-8") as f:
        f.write(
            "# Answers to grade\n\nEach answer is from a real test taker. For photo tasks "
            "the photo is not available. Judge the language and how well the answer does "
            "the task.\n\n"
        )
        for x in samples:
            f.write(f"## {x['id']} ({x['task']}, {x['skill']})\n\n{x['text']}\n\n")
    keys = ("id", "task", "skill", "score", "held_out")
    (out / "key.json").write_text(json.dumps([{k: x[k] for k in keys} for x in samples], indent=1))
    print(f"{len(samples)} samples written to {out}")


if __name__ == "__main__":
    main()
