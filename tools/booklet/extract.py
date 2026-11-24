"""Read the official DET Sample Questions booklet into a question bank.

Usage:
    uv run --with pymupdf --with zxing-cpp --with pillow \\
        python tools/booklet/extract.py <booklet PDF> .cache/booklet

Writes bank.json (every question with its answer), photos/ and audio/. The audio
comes from the booklet's QR codes, which link to Duolingo's MP3 files. The booklet
is copyrighted, so the output belongs in .cache/, never in the repository. Then run
tools/booklet/make_rounds.py to build practice rounds from the bank.

Booklet: "DET Sample Questions - Full" (March 2025),
https://englishtest-static.duolingo.com/media/resources/GPN%20DET%20Sample%20Questions%20-%20Full.pdf
"""

from __future__ import annotations

import difflib
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import fitz  # pymupdf
import zxingcpp
from PIL import Image

# PDF pages (1-based) of each part of the booklet.
QUESTIONS = {
    "read_complete": (7, 12),
    "read_select": (13, 16),
    "fill_blanks": (17, 19),
    "listen_type": (20, 22),
    "interactive_reading": (28, 73),
    "interactive_listening": (76, 125),
    "write_photo": (126, 133),
    "speak_photo": (134, 141),
    "interactive_writing": (142, 149),
    "read_then_speak": (150, 152),
    "listen_then_speak": (153, 154),
    "writing_sample": (155, 157),
    "speaking_sample": (158, 160),
}
ANSWERS = (161, 189)
# The answer key cuts Read and Complete 10 short at a page break. The question shows the
# rest of the text, and its two gaps can only be "of" and "density".
RC_FIXES = {
    10: (
        "a point of",
        "a point of infinite density. Black holes can be found at the "
        "center of most galaxies, including our own Milky Way.",
    )
}
LTS_TRANSCRIPTS = (192, 193)
NOISE = re.compile(
    r"^\s*(\d+|Sample Questions|QUESTIONS?( \d+)?|Key information.*|Answers|"
    r"Conversations with an? .*|[A-Z][A-Z :,]{6,})\s*$"
)
ITEM = re.compile(r"(?m)^\s*(\d+)\)\s*")
OPTION = re.compile(r"(?m)^\s*([a-f])\)\s+")


def clean(text: str) -> str:
    """Fix ligatures and odd spaces, and join the lines of a paragraph."""
    text = unicodedata.normalize("NFKC", text).replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def page_text(doc, first: int, last: int) -> str:
    lines = []
    for n in range(first, last + 1):
        lines += [x for x in doc[n - 1].get_text().splitlines() if not NOISE.match(x)]
    return unicodedata.normalize("NFKC", "\n".join(lines))


def line_text(doc, first: int, last: int) -> str:
    """Page text rebuilt from the position of each letter.

    Some passages store parts of their lines in reverse order, so the normal text has
    them backwards. Use this only for pages with one column."""
    lines = []
    for n in range(first, last + 1):
        chars = [
            c
            for b in doc[n - 1].get_text("rawdict")["blocks"]
            for ln in b.get("lines", [])
            for s in ln["spans"]
            for c in s["chars"]
        ]
        rows: dict[int, list] = {}
        for c in chars:
            y = round(c["origin"][1])
            key = next((k for k in (y, y - 1, y + 1, y - 2, y + 2) if k in rows), y)
            rows.setdefault(key, []).append(c)
        for y in sorted(rows):
            text, last_x = "", None
            for c in sorted(rows[y], key=lambda c: c["origin"][0]):
                x0, _, x1, _ = c["bbox"]
                if last_x is not None and x0 - last_x > 1.5 and not text.endswith(" "):
                    text += " "
                text += c["c"]
                last_x = x1
            if not NOISE.match(text):
                lines.append(text)
    return unicodedata.normalize("NFKC", "\n".join(lines))


def numbered(text: str) -> list[tuple[int, str]]:
    """The '1) ...' items of a text, in order."""
    marks = list(ITEM.finditer(text))
    return [
        (int(m.group(1)), text[m.end() : marks[i + 1].start() if i + 1 < len(marks) else None])
        for i, m in enumerate(marks)
    ]


def runs(items: list[tuple[int, str]]) -> list[list[str]]:
    """Split numbered items where the numbering starts again at 1."""
    out: list[list[str]] = []
    for n, text in items:
        if n == 1 or not out:
            out.append([])
        out[-1].append(clean(text))
    return out


def options(text: str) -> tuple[str, dict[str, str]]:
    """Split '... a) one b) two' into the text before the options and the options."""
    marks = list(OPTION.finditer(text))
    if not marks:
        return clean(text), {}
    opts = {
        m.group(1): clean(text[m.end() : marks[i + 1].start() if i + 1 < len(marks) else None])
        for i, m in enumerate(marks)
    }
    return clean(text[: marks[0].start()]), opts


# ---------- words with missing letters ----------


def _alnum(text: str) -> tuple[str, list[int]]:
    """The letters and digits of a text in lower case, and the index of each in the text."""
    chars, where = [], []
    for i, c in enumerate(text):
        if c.isalnum():
            chars.append(c.lower())
            where.append(i)
    return "".join(chars), where


BLANK = re.compile(r"([A-Za-z]*)\s?((?:_\s?)+)")
TOKEN = re.compile(r"([A-Za-z0-9’']*)\s?((?:_\s?)+)|([A-Za-z0-9’']+)")


def fill_gaps(question: str, answer: str) -> tuple[str, int]:
    """Mark the unfinished words of a question in the answer text as {start|rest}.

    The question shows 'Wi_ _ a look o_ determination' and the answer gives the full
    text. The two texts are aligned word by word, so small differences between them
    and unreadable parts of the question only lose those gaps. Returns the marked
    answer text and the number of question gaps that could not be placed."""
    q = [
        (m.group(1), m.group(2).count("_")) if m.group(2) else m.group(3).lower()
        for m in TOKEN.finditer(question)
    ]
    a = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"[A-Za-z0-9’']+", answer)]
    an = [w.lower() for _, _, w in a]
    qn = [f"\0{i}" if isinstance(t, tuple) else t for i, t in enumerate(q)]
    same: dict[int, int] = {}  # question word -> the same word in the answer
    for blk in difflib.SequenceMatcher(None, qn, an, autojunk=False).get_matching_blocks():
        same |= {blk.a + k: blk.b + k for k in range(blk.size)}
    gaps: dict[int, int] = {}  # answer word -> letters shown
    placed: dict[int, int] = {}  # question gap -> answer word
    for i, t in enumerate(q):
        if not isinstance(t, tuple) or not t[0]:
            continue
        prefix, n = t[0].lower(), t[1]
        lo = max([same[k] + 1 for k in same if k < i] + [0])
        hi = min([same[k] for k in same if k > i] + [len(an)])
        lo = max([lo] + [k + 1 for k in gaps])  # gaps come in order
        best = next(
            (
                k
                for k in range(lo, hi)
                if an[k].startswith(prefix) and len(an[k]) == len(prefix) + n
            ),
            None,
        )
        if best is not None:
            gaps[best] = len(prefix)
            placed[i] = best
    # A common word can anchor to the wrong place. Search the unplaced gaps again between
    # the gaps around them.
    for i, t in enumerate(q):
        if not isinstance(t, tuple) or not t[0] or i in placed:
            continue
        prefix, n = t[0].lower(), t[1]
        lo = max([placed[k] + 1 for k in placed if k < i] + [0])
        hi = min([placed[k] for k in placed if k > i] + [len(an)])
        best = next(
            (
                k
                for k in range(lo, hi)
                if an[k].startswith(prefix) and len(an[k]) == len(prefix) + n
            ),
            None,
        )
        if best is not None:
            gaps[best] = len(prefix)
            placed[i] = best
    out, last = [], 0
    for j, cut in sorted(gaps.items()):
        start, end, _ = a[j]
        out += [answer[last:start], "{", answer[start : start + cut], "|"]
        out += [answer[start + cut : end], "}"]
        last = end
    lost = sum(isinstance(t, tuple) for t in q) - len(gaps)
    return "".join(out + [answer[last:]]), lost


# ---------- one parser per task type ----------


def read_complete(qtext: str, answers: list[str]) -> list[dict]:
    out = []
    for (n, q), a in zip(numbered(qtext), answers, strict=False):
        if n in RC_FIXES and a.endswith(RC_FIXES[n][0]):
            a = a.removesuffix(RC_FIXES[n][0]) + RC_FIXES[n][1]
        title, _, passage = a.removeprefix("Title: ").partition(". ")
        marked, lost = fill_gaps(clean(q), passage)
        if lost:
            print(f"read_complete {n}: {lost} gaps could not be placed")
        out.append({"n": n, "title": title, "passage": marked})
    return out


def read_select(qtext: str, answers: list[str]) -> list[dict]:
    return [
        {"n": n, "word": clean(w), "real": a.startswith("Yes")}
        for (n, w), a in zip(numbered(qtext), answers, strict=False)
    ]


def fill_blanks(qtext: str, answers: list[str]) -> list[dict]:
    out = []
    for (n, q), word in zip(numbered(qtext), answers, strict=False):
        q = clean(q)
        m = BLANK.search(q)
        if not m or not word.lower().startswith(m.group(1).lower()) or not m.group(1):
            print(f"fill_blanks {n}: cannot match '{word}', skipped")
            continue
        cut = len(m.group(1))
        sentence = q[: m.start()] + "{" + word[:cut] + "|" + word[cut:] + "}" + q[m.end() :]
        out.append({"n": n, "sentence": re.sub(r"\s+([.,!?])", r"\1", sentence).strip()})
    return out


def labels(page) -> list[tuple[int, fitz.Rect]]:
    """The '12)' labels of a page and where they are."""
    return [
        (int(w[4][:-1]), fitz.Rect(w[:4]))
        for w in page.get_text("words")
        if re.fullmatch(r"\d+\)", w[4])
    ]


def qr_codes(doc, first: int, last: int) -> dict[int, str]:
    """Question number -> the URL of its QR code. A label sits left of its code."""
    out = {}
    for n in range(first, last + 1):
        page = doc[n - 1]
        scale = 300 / 72
        pix = page.get_pixmap(dpi=300, alpha=False)
        img = Image.frombytes("RGB", (pix.w, pix.h), pix.samples)
        codes = []
        for r in zxingcpp.read_barcodes(img):
            xs = [p.x / scale for p in (r.position.top_left, r.position.bottom_left)]
            ys = [p.y / scale for p in (r.position.top_left, r.position.bottom_right)]
            codes.append((min(xs), sum(ys) / 2, r.text))
        for num, rect in labels(page):
            row = [c for c in codes if abs(c[1] - (rect.y0 + rect.y1) / 2) < 30 and c[0] > rect.x1]
            if row:
                out[num] = min(row, key=lambda c: c[0])[2]
    return out


def photos(doc, first: int, last: int, out_dir: Path, kind: str) -> dict[int, str]:
    """Save each photo as <kind>-<n>.jpg.

    Each photo has its number in a corner. The '12)' labels next to the photos have
    mistakes (two say 31), so the corner number decides."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = {}
    for n in range(first, last + 1):
        page = doc[n - 1]
        numbers = [
            (int(w[4]), fitz.Point(w[0], w[1])) for w in page.get_text("words") if w[4].isdigit()
        ]
        for info in page.get_image_info(xrefs=True):
            box = fitz.Rect(info["bbox"])
            inside = [num for num, at in numbers if at in box]
            if not inside:  # no number in the corner: use the label beside the photo
                cy = (box.y0 + box.y1) / 2
                inside = [
                    num
                    for num, r in labels(page)
                    if abs((r.y0 + r.y1) / 2 - cy) < 20
                    and min(abs(r.x1 - box.x0), abs(r.x0 - box.x1)) < 40
                ]
            if not info["xref"] or len(inside) != 1:
                continue
            pix = fitz.Pixmap(doc, info["xref"])
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            if pix.alpha:
                pix = fitz.Pixmap(pix, 0)
            name = f"{kind}-{inside[0]:02d}.jpg"
            pix.save(out_dir / name, jpg_quality=92)
            saved[inside[0]] = name
    return saved


def prompts(qtext: str) -> list[dict]:
    return [{"n": n, "prompt": clean(t)} for n, t in numbered(qtext)]


def interactive_writing(qtext: str) -> list[dict]:
    out = []
    for n, t in numbered(qtext):
        prompt, _, rest = t.partition("Follow-up Questions:")
        follow = [clean(x) for x in re.split(r"\n\s*(?=\S)", rest) if clean(x)]
        # A follow-up question can wrap over lines: join lines that do not end a sentence.
        joined: list[str] = []
        for line in follow:
            if joined and not joined[-1].endswith(("?", ".")):
                joined[-1] += " " + line
            else:
                joined.append(line)
        out.append({"n": n, "prompt": clean(prompt), "follow_ups": joined})
    return out


def interactive_reading(qtext: str, answers: dict[int, str]) -> list[dict]:
    out = []
    parts = re.split(r"(?m)^\s*(\d+)\.(\d)\)\s*", qtext)
    qs: dict[int, dict[int, str]] = {}
    for i in range(1, len(parts), 3):
        qs.setdefault(int(parts[i]), {})[int(parts[i + 1])] = parts[i + 2]
    for n, q in sorted(qs.items()):
        try:
            out.append(_reading(n, q, answers[n]))
        except (KeyError, ValueError, IndexError) as e:
            print(f"interactive_reading {n}: {e}, skipped")
    return out


def _choice(opts: dict[str, str], key: str) -> dict:
    """The options with the right one first. The key gives a letter and the text of the
    option. The booklet sometimes has the wrong letter, so the text decides."""
    m = re.match(r"\s*([a-f])\)\s*(.*)", clean(key))
    letter, text = (m.group(1), m.group(2)) if m else ("", clean(key))
    if text:

        def score(k: str) -> float:
            a, b = _alnum(opts[k])[0], _alnum(text)[0]
            if len(b) > 20 and a.startswith(b):
                return 1.0
            return difflib.SequenceMatcher(None, a, b).ratio()

        best = max(opts, key=score)
        if score(best) > 0.8 or not letter:
            letter = best
    return {"answer": opts[letter], "wrong": [v for k, v in opts.items() if k != letter]}


def _reading(n: int, q: dict[int, str], key: str) -> dict:
    item = rf"(?<![\d.]){n}\.(\d)\)"
    k = {
        int(m.group(1)): m.group(2) for m in re.finditer(rf"{item}\s*(.*?)(?={item}|$)", key, re.S)
    }
    words = [
        clean(w) for w in re.findall(rf"{n}\.1\.\d+\)\s*(.*?)(?=\s*{n}\.1\.\d+\)|$)", k[1], re.S)
    ]
    # 1: the passage with numbered gaps, then one list of words for each gap
    body = q[1].split(":", 1)[1].replace("Select the best option for each missing word:", "")
    first = re.search(r"(?m)^\s*1\)\s+\S+/", body)
    passage_q, lists = body[: first.start()], body[first.start() :]
    choices = [[clean(w) for w in t.split("/")] for _, t in numbered(lists)]
    chunks = re.split(r"\s*\b\d+\)\s*", passage_q)
    if not len(chunks) - 1 == len(words) == len(choices):
        raise ValueError(f"{len(chunks) - 1} gaps, {len(words)} answers, {len(choices)} lists")
    # 2: the full first part, then the rest after the missing sentence
    head, opts = options(q[2].split(":", 1)[1].split("Click and drag")[0])
    filled = " ".join(
        clean(c) + (" " + w if i < len(words) else "")
        for i, (c, w) in enumerate(zip(chunks, [*words, ""], strict=False))
    )
    stream, where = _alnum(head)
    tail = _alnum(chunks[-1])[0][-40:] or _alnum(words[-1])[0]
    if not stream.startswith(_alnum(filled)[0]):  # the booklet changed a word: trust the key
        print(
            f"interactive_reading {n}: the passage differs from the key, the key's words are used"
        )
        first_part = clean(filled)
        end = stream.find(tail, len(_alnum(chunks[0])[0])) + len(tail)
    else:
        end = len(_alnum(filled)[0])
        first_part = None
    if end < len(tail):
        raise ValueError("cannot find the end of the first part")
    cut = where[end - 1] + 1
    cut += len(head[cut:]) - len(head[cut:].lstrip(".,;:!?”’\")'"))
    rest = head[cut:].strip()
    if first_part is None:
        first_part = head[:cut].strip()
        # mark each gap in the first part: the right word first
        marked, pos, at = "", 0, 0
        w2 = _alnum(first_part)[1]
        for c, w, opts_w in zip(chunks, words, choices, strict=False):
            at += len(_alnum(c)[0])
            start, end = w2[at], w2[at + len(_alnum(w)[0]) - 1] + 1
            marked += (
                first_part[pos:start]
                + "{"
                + "|".join([first_part[start:end], *_wrong(w, opts_w)])
                + "}"
            )
            pos, at = end, at + len(_alnum(w)[0])
        marked += first_part[pos:]
    else:
        marked = " ".join(
            clean(c) + (" {" + "|".join([w, *_wrong(w, o)]) + "}" if w else "")
            for c, w, o in zip(chunks, [*words, ""], [*choices, []], strict=False)
        ).strip()
        marked = re.sub(r"\s+([.,;:!?])", r"\1", marked)
    # 3 and 4: highlight questions. 5: main idea. 6: title.
    hl_q = [clean(q[3]), clean(q[4])]
    _, idea = options(q[5])
    _, title = options(q[6])
    full = clean(first_part + " " + opts[k[2].strip()[0]] + " " + rest)
    highlights = []
    for question, answer in zip(hl_q, (clean(k[3]), clean(k[4])), strict=False):
        answer = answer.rstrip(" .")
        if clean(answer) not in full:
            answer = _closest(full, answer)
        highlights.append({"question": question, "answer": answer})
    return {
        "n": n,
        "passage": marked,
        "missing_sentence": _choice(opts, k[2]),
        "rest": rest,
        "highlight": highlights,
        "main_idea": _choice(idea, k[5]),
        "best_title": _choice(title, k[6]),
    }


def _wrong(word: str, choices: list[str]) -> list[str]:
    wrong = [x for x in choices if x.lower() != word.lower()]
    if len(wrong) == len(choices):
        raise ValueError(f"'{word}' is not in its list")
    return wrong


def _closest(full: str, answer: str) -> str:
    """The text in the passage that matches an answer up to spaces, case and punctuation."""
    stream, where = _alnum(full)
    i = stream.find(_alnum(answer)[0])
    if i >= 0:
        return full[where[i] : where[i + len(_alnum(answer)[0]) - 1] + 1]
    # The booklet changed the passage after writing the key: take the most similar words.
    words = list(re.finditer(r"\S+", full))
    size = len(answer.split())
    best, score = None, 0.0
    for size_ in range(max(1, size - 2), size + 3):
        for i in range(len(words) - size_ + 1):
            span = full[words[i].start() : words[i + size_ - 1].end()].rstrip(".,;:")
            r = difflib.SequenceMatcher(None, span.lower(), answer.lower()).ratio()
            if r > score:
                best, score = span, r
    if score < 0.7:
        raise ValueError(f"highlight answer '{answer[:40]}' is not in the passage")
    print(f"highlight '{answer}' is not in the passage, using '{best}'")
    return best


def interactive_listening(qtext: str, answers: dict[int, str]) -> list[dict]:
    out = []
    parts = re.split(r"(?m)^\s*QUESTION (\d+)\s*$", qtext)
    if len(parts) < 3:  # NOISE removed the headers: split on the scenarios instead
        parts = [""] + [
            x for i, s in enumerate(re.split(r"(?=Scenario:)", qtext)[1:], 1) for x in (str(i), s)
        ]
    for i in range(1, len(parts), 2):
        n = int(parts[i])
        try:
            out.append(_listening(n, parts[i + 1], answers[n]))
        except (KeyError, ValueError) as e:
            print(f"interactive_listening {n}: {e}, skipped")
    return out


TURN = re.compile(r"(?m)^\s*(You|Classmate|Professor|Student):\s*")


def _listening(n: int, q: str, key: str) -> dict:
    scenario = clean(re.split(TURN, q.split("Scenario:", 1)[1])[0])
    chosen = re.findall(r"(?m)^You:\s*(\S.*)$", key)
    marks = list(TURN.finditer(q))
    turns, partner = [], "student"
    for i, m in enumerate(marks):
        text = q[m.end() : marks[i + 1].start() if i + 1 < len(marks) else None]
        head, opts = options(text)
        if m.group(1) != "You":
            partner = "professor" if m.group(1) == "Professor" else "student"
            turns.append({"partner": head})
        if opts:  # the booklet sometimes leaves out the "You:" before the options
            mine = sum("you" in t for t in turns)
            if mine >= len(chosen):
                raise ValueError("more choices than answers")
            turns.append({"you": _choice(opts, chosen[mine])})
    mine = sum("you" in t for t in turns)
    if mine != len(chosen):
        raise ValueError(f"{mine} choices but {len(chosen)} answers")
    return {"n": n, "partner": partner, "scenario": scenario, "conversation": turns}


def answer_key(doc) -> dict:
    text = page_text(doc, *ANSWERS)
    head, _, tail = text.partition("\nQuestion 1\n")
    lists = runs(numbered(head))
    rc, rs, fb, lt = lists[:4]
    blocks = re.split(r"(?m)^Question (\d+)\s*$", "Question 1\n" + tail)
    reading: dict[int, str] = {}
    listening: dict[int, str] = {}
    target = reading
    for i in range(1, len(blocks), 2):
        n = int(blocks[i])
        if n in target and target is reading:
            target = listening
        target[n] = blocks[i + 1].split("Sample summary:")[0]
    lts = [clean(t.split("Question:")[0]) for _, t in numbered(page_text(doc, *LTS_TRANSCRIPTS))]
    return {"rc": rc, "rs": rs, "fb": fb, "lt": lt, "ir": reading, "il": listening, "lts": lts}


def download(url: str, out: Path) -> bool:
    if out.is_file():
        return True
    m = re.match(r"https://drive\.google\.com/file/d/([\w-]+)", url)
    if m:
        url = f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    req = urllib.request.Request(
        urllib.parse.quote(url, safe=":/?=&%"), headers={"User-Agent": "det-coach"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
    except OSError as e:
        print(f"could not download {url}: {e}")
        return False
    if not data.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
        print(f"{url} is not an MP3 file, skipped")
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return True


def main(pdf: Path, out: Path) -> None:
    doc = fitz.open(pdf)
    key = answer_key(doc)
    q = {k: page_text(doc, *v) for k, v in QUESTIONS.items()}
    bank: dict[str, list[dict]] = {
        "read_complete": read_complete(line_text(doc, *QUESTIONS["read_complete"]), key["rc"]),
        "read_select": read_select(q["read_select"], key["rs"]),
        "fill_blanks": fill_blanks(q["fill_blanks"], key["fb"]),
        "interactive_reading": interactive_reading(q["interactive_reading"], key["ir"]),
        "interactive_listening": interactive_listening(q["interactive_listening"], key["il"]),
        "interactive_writing": interactive_writing(q["interactive_writing"]),
    }
    for kind in ("read_then_speak", "writing_sample", "speaking_sample"):
        bank[kind] = prompts(q[kind])
    for kind in ("write_photo", "speak_photo"):
        saved = photos(doc, *QUESTIONS[kind], out / "photos", kind.replace("_", "-"))
        bank[kind] = [{"n": n, "photo": name} for n, name in sorted(saved.items())]
    for kind, texts in (("listen_type", key["lt"]), ("listen_then_speak", key["lts"])):
        urls = qr_codes(doc, *QUESTIONS[kind])
        items = []
        for n, text in enumerate(texts, 1):
            item = {"n": n, "text": text}
            name = f"{kind.replace('_', '-')}-{n:02d}.mp3"
            if n in urls and download(urls[n], out / "audio" / name):
                item["audio"] = name
            items.append(item)
        bank[kind] = items
    out.mkdir(parents=True, exist_ok=True)
    (out / "bank.json").write_text(json.dumps(bank, indent=1, ensure_ascii=False) + "\n")
    for kind, items in bank.items():
        extra = f", {sum('audio' in i for i in items)} with audio" if "listen" in kind else ""
        print(f"{kind}: {len(items)}{extra}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
