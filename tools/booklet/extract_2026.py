"""Read an official 2026 DET practice booklet into a question bank.

Usage:
    uv run --with pymupdf --with zxing-cpp --with pillow \\
        python -I tools/booklet/extract_2026.py <booklet PDF> .cache/vol5

Reads "DET Practice Questions Volume 4, 2026" and "Volume 5, 2026" (same publisher as
the booklet that extract.py reads, but a different layout). Writes bank.json in the
format of extract.py, photos/ and audio/. The audio comes from the QR codes of the
booklet. The booklet is copyrighted, so the output belongs in .cache/, never in the
repository.

New in these booklets, and so new in bank.json:
- interactive_listening items have "complete" (Listen and Complete), "scenario_audio"
  and an "audio" file for each partner turn.
- interactive_speaking: one item for each set of questions, with "topics".
- read_then_speak items can have "bullets".
- "notes": what the booklet has that the bank cannot hold, and what looked wrong.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fitz  # noqa: E402  (pymupdf)
import zxingcpp  # noqa: E402
from extract import (  # noqa: E402
    _alnum,
    _choice,
    _wrong,
    clean,
    fill_gaps,
    line_text,
    numbered,
    options,
)
from PIL import Image  # noqa: E402

# The title of each part in the question pages, in the order of the booklet.
TITLES = {
    "read_select": "Read and Select",
    "fill_blanks": "Fill in the Blanks",
    "read_complete": "Read and Complete",
    "listen_type": "Listen and Type",
    "interactive_reading": "Interactive Reading",
    "interactive_listening": "Interactive Listening",
    "write_photo": "Write About the Photo",
    "interactive_writing": "Interactive Writing",
    "speak_photo": "Speak About the Photo",
    "read_then_speak": "Read Then Speak",
    "interactive_speaking": "Interactive Speaking",
    "writing_sample": "Writing Sample",
    "speaking_sample": "Speaking Sample",
}
# Page headers and footers.
NOISE = re.compile(
    r"^\s*(\d{1,3}|[ivx]+|Practice Questions|DET Practice Questions Volume \d.*|Answers)\s*$"
)
QUESTION = re.compile(r"(?m)^\s*Question (\d+)\b[^\n]*$")
MP3 = (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")

notes: list[str] = []


def note(text: str) -> None:
    print(text)
    notes.append(text)


# ---------- pages ----------


CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def norm(text: str) -> str:
    """NFKC, without the control characters that the booklet puts before some words."""
    return CONTROL.sub("", unicodedata.normalize("NFKC", text).replace("\u00a0", " "))


def parts(doc) -> tuple[dict[str, tuple[int, int]], tuple[int, int]]:
    """The first and last page (1-based) of each part, and of the answers."""
    start: dict[str, int] = {}
    answers = end = 0
    for i, page in enumerate(doc):
        if i < 8:  # the contents pages name every part
            continue
        text = page.get_text()
        lines = [norm(x).strip() for x in text.splitlines()]
        if "Key information" in text:
            for kind, title in TITLES.items():
                if kind not in start and (
                    title in lines or title.replace(" Then", ", Then") in lines
                ):
                    start[kind] = i + 1
        if "Answers" in lines and len(start) == len(TITLES) and not answers:
            answers = i + 1
        if "Additional Resources" in lines and answers:
            end = i
            break
    missing = set(TITLES) - set(start)
    if missing or not answers:
        sys.exit(f"cannot find the parts {missing or 'Answers'} in the booklet")
    order = sorted(start.items(), key=lambda x: x[1])
    pages = {
        kind: (first, (order[j + 1][1] if j + 1 < len(order) else answers) - 1)
        for j, (kind, first) in enumerate(order)
    }
    return pages, (answers, end)


PAGES: dict[int, str] = {}  # page -> its text, to name the page of a problem
RANGES: dict[str, tuple[int, int]] = {}


def page_of(kind: str, needle: str) -> str:
    """' (page 12)': the first page of a part that has the needle in its text."""
    first, last = RANGES.get(kind, (0, -1))
    needle = clean(needle)
    for n in range(first, last + 1):
        if needle in PAGES.get(n, ""):
            return f" (page {n})"
    return ""


def page_text(doc, first: int, last: int) -> str:
    lines = []
    for n in range(first, last + 1):
        lines += [x for x in norm(doc[n - 1].get_text()).splitlines() if not NOISE.match(x)]
    return "\n".join(lines)


def answer_key(doc, first: int, last: int) -> dict[str, str]:
    """The answers, split into parts. Each part starts with a line '<en space> Title'."""
    out: dict[str, list[str]] = {}
    current = None
    for n in range(first, last + 1):
        for raw in doc[n - 1].get_text().splitlines():
            if raw.startswith("\u2002"):
                title = norm(raw).strip().removesuffix(" (Transcripts)")
                current = next((k for k, t in TITLES.items() if t == title), None)
                if current is None:
                    note(f"answer key page {n}: unknown part '{title}'")
                out.setdefault(current or title, [])
                continue
            line = norm(raw)
            if current and not NOISE.match(line):
                out[current].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def key_items(text: str) -> list[tuple[int, str]]:
    """The '1) ...' items of a part of the key. A label can follow a tab in the line."""
    marks = list(re.finditer(r"(?m)(?:^|(?<=\t))[ \t]*(\d+)\)\s*", text))
    return [
        (int(m.group(1)), text[m.end() : marks[i + 1].start() if i + 1 < len(marks) else None])
        for i, m in enumerate(marks)
    ]


def questions(text: str) -> dict[int, str]:
    """The 'Question 3' blocks of a text."""
    marks = list(QUESTION.finditer(text))
    return {
        int(m.group(1)): text[m.end() : marks[i + 1].start() if i + 1 < len(marks) else None]
        for i, m in enumerate(marks)
    }


# ---------- QR codes ----------


def qr_codes(doc, first: int, last: int) -> list[tuple[int, float, float, str]]:
    """(page, x, y of the centre, text) of every QR code in the pages."""
    out = []
    scale = 300 / 72
    for n in range(first, last + 1):
        pix = doc[n - 1].get_pixmap(dpi=300, alpha=False)
        img = Image.frombytes("RGB", (pix.w, pix.h), pix.samples)
        for r in zxingcpp.read_barcodes(img):
            p = r.position
            pts = (p.top_left, p.top_right, p.bottom_left, p.bottom_right)
            x = sum(q.x for q in pts) / 4 / scale
            y = sum(q.y for q in pts) / 4 / scale
            if not r.text.startswith("http"):  # a false code inside another code
                continue
            out.append((n, x, y, r.text))
    return out


def words(doc, first: int, last: int, pattern: str) -> list[tuple[int, fitz.Rect, str]]:
    """(page, box, text) of the words that match a pattern. 'Question 3' is one word."""
    out = []
    for n in range(first, last + 1):
        ws = doc[n - 1].get_text("words")
        for i, w in enumerate(ws):
            text = w[4]
            if text == "Question" and i + 1 < len(ws) and re.match(r"\d+", ws[i + 1][4]):
                text = "Question " + re.match(r"\d+", ws[i + 1][4]).group(0)
            if re.fullmatch(pattern, text):
                out.append((n, fitz.Rect(w[:4]), text))
    return out


def beside(labels, codes) -> dict[tuple, str]:
    """Label -> the URL of the QR code right of it on the same row.

    labels are (page, box, key)."""
    out = {}
    for page, rect, key in labels:
        cy = (rect.y0 + rect.y1) / 2
        row = [c for c in codes if c[0] == page and abs(c[2] - cy) < 40 and c[1] > rect.x1]
        if row:
            out[key] = min(row, key=lambda c: c[1])[3]
    return out


def download(url: str, out: Path) -> str:
    """Save an MP3 file. Returns '' or the reason it failed."""
    if out.is_file():
        return ""
    m = re.match(r"https://drive\.google\.com/file/d/([\w-]+)", url)
    if m:
        url = f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    # Keep '+' as it is: the server reads %2B as a different file name.
    req = urllib.request.Request(
        urllib.parse.quote(url, safe=":/?=&%+()"), headers={"User-Agent": "det-coach"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except OSError as e:
        return f"cannot download {url}: {e}"
    if not data.startswith(MP3):
        return f"{url} is not an MP3 file ({data[:20]!r})"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return ""


class Audio:
    def __init__(self, out: Path) -> None:
        self.dir = out / "audio"
        self.failed: list[str] = []
        self.saved = 0

    def get(self, url: str, name: str) -> str:
        problem = download(url, self.dir / name)
        if problem:
            note(f"audio {name}: {problem}")
            self.failed.append(name)
            return ""
        self.saved += 1
        return name


# ---------- the parts with one word or sentence ----------


def read_select(qtext: str, key: str) -> list[dict]:
    answers = {n: clean(t) for n, t in key_items(key)}
    out = []
    for n, w in numbered(qtext):
        word = clean(w)
        m = re.fullmatch(r"(\S+) \((real|fake)\)", answers.get(n, ""))
        if not m or m.group(1) != word:
            note(
                f"read_select {n}{page_of('read_select', word)}: '{word}' does not match "
                f"the key '{answers.get(n)}'"
            )
            if not m:
                continue
        out.append({"n": n, "word": word, "real": m.group(2) == "real"})
    return out


BLANK = re.compile(r"([A-Za-z]*)\s?((?:_\s?)+)")


def fill_blanks(qtext: str, key: str) -> list[dict]:
    """Volume 5 gives the whole sentence in the key, Volume 4 only the word."""
    answers = {n: clean(t) for n, t in key_items(key)}
    out = []
    for n, q in numbered(qtext):
        q = clean(q)
        a = answers.get(n, "")
        m = BLANK.search(q)
        if not m or not a:
            note(f"fill_blanks {n}: no gap in '{q}' or no answer '{a}', skipped")
            continue
        shown, size = m.group(1), m.group(2).count("_")
        if len(a.split()) > 3:  # a sentence
            marked, lost = fill_gaps(q, a)
            gap = re.search(r"\{([^{}|]*)\|([^{}]*)\}", marked)
            word = gap.group(1) + gap.group(2) if gap and not lost else ""
        else:  # a word, or 'organizing / organising'
            words = [w.strip() for w in a.split("/")]
            fits = [
                w
                for w in words
                if w.lower().startswith(shown.lower()) and len(w) == len(shown) + size
            ]
            word = (fits or [""])[0]
            if len(words) > 1:
                note(f"fill_blanks {n}: the key accepts {words}, the bank keeps '{word}'")
        if not word or not shown:
            note(
                f"fill_blanks {n}{page_of('fill_blanks', q[:25])}: cannot find the word of '{q}' "
                f"in the key '{a}', skipped"
            )
            continue
        space = " " if m.group(0).endswith(" ") else ""
        gap_text = "{" + word[: len(shown)] + "|" + word[len(shown) :] + "}"
        sentence = q[: m.start()] + gap_text + space + q[m.end() :]
        sentence = re.sub(r"\s+([.,!?;:])", r"\1", sentence).strip()
        # The question has a stray letter after the full stop in one item.
        sentence = re.sub(r"([.!?])[a-z]$", r"\1", sentence)
        plain = re.sub(r"\{([^{}|]*)\|([^{}]*)\}", r"\1\2", sentence)
        if len(a.split()) > 3 and _alnum(plain)[0] != _alnum(a)[0]:
            note(
                f"fill_blanks {n}{page_of('fill_blanks', q[:25])}: the question differs from the "
                f"key: '{plain}' / '{a}'"
            )
        out.append({"n": n, "sentence": sentence})
    return out


def read_complete(qtext: str, key: str) -> list[dict]:
    answers = dict(numbered(key))
    out = []
    for n, q in numbered(qtext):
        a = answers.get(n)
        if a is None:
            note(f"read_complete {n}: not in the key, skipped")
            continue
        q_title, _, q_text = q.strip().partition("\n")
        title, _, passage = a.strip().partition("\n")
        title, passage = clean(title), clean(passage)
        page = page_of("read_complete", f"{n}) {clean(q_title)}")
        if clean(q_title) != title:
            note(f"read_complete {n}{page}: the title '{clean(q_title)}' is '{title}' in the key")
        marked, lost = fill_gaps(clean(q_text), passage)
        if lost:
            shown = [m.group(0).strip() for m in BLANK.finditer(clean(q_text)) if m.group(1)]
            kept = [m.group(1) for m in re.finditer(r"\{([^{}|]*)\|", marked)]
            ops = difflib.SequenceMatcher(
                None, [x.split("_")[0].lower() for x in shown], [k.lower() for k in kept]
            )
            gone = [
                shown[i]
                for tag, i1, i2, _, _ in ops.get_opcodes()
                if tag in ("delete", "replace")
                for i in range(i1, i2)
            ]
            note(
                f"read_complete {n}{page}: the key does not fit the gaps {gone}, "
                "so those words have no gap"
            )
        out.append({"n": n, "title": title, "passage": marked})
    return out


def listen_type(doc, pages: tuple[int, int], key: str, audio: Audio) -> list[dict]:
    codes = qr_codes(doc, *pages)
    urls = beside([(p, r, int(t[:-1])) for p, r, t in words(doc, *pages, r"\d+\)")], codes)
    out = []
    for n, text in key_items(key):
        item = {"n": n, "text": clean(text)}
        if n in urls:
            name = audio.get(urls[n], f"listen-type-{n:02d}.mp3")
            if name:
                item["audio"] = name
        else:
            note(f"listen_type {n}: no QR code")
        out.append(item)
    if len(codes) != len(out):
        note(f"listen_type: {len(codes)} QR codes for {len(out)} sentences")
    return out


# ---------- Interactive Reading ----------

IR_HEADS = (
    r"(?mi)^\s*(Complete the Sentences|Complete the passage|Highlight the Answer|"
    r"Highlight the text in the passage.*|Identify the Idea|Title the Passage)\s*:?\s*$"
)


def _segment(text: str, start: int, stops: list[int]) -> str:
    return text[start : min([s for s in stops if s > start] + [len(text)])]


def _no_heads(text: str) -> str:
    text = re.sub(IR_HEADS, "", text)
    return re.sub(r"(?m)^\s*Select the (best|Idea).*$", "", text)


def _highlight(full: str, answer: str) -> str | None:
    """The words of the text that a highlight answer of the key gives.

    The key can differ from the text in case and punctuation, and can add words that
    are not in the text. Then the longest run of its words that is in the text wins, if
    it has at least half of the words."""
    stream, where = _alnum(full)
    tokens = re.findall(r"[A-Za-z0-9’']+", answer)
    best = None
    for size in range(len(tokens), max(1, (len(tokens) + 1) // 2) - 1, -1):
        for i in range(len(tokens) - size + 1):
            target = _alnum(" ".join(tokens[i : i + size]))[0]
            at = stream.find(target)
            if target and at >= 0:
                best = full[where[at] : where[at + len(target) - 1] + 1]
                break
        if best:
            return best
    return None


def interactive_reading(qtext: str, key: str) -> list[dict]:
    keys: dict[int, dict] = {}
    marks = list(re.finditer(r"(?m)^\s*(\d+)\.(\d)(?:\.(\d+))?\)\s*", key))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(key)
        text = clean(QUESTION.sub("", key[m.end() : end]))
        k = keys.setdefault(int(m.group(1)), {"words": {}})
        if m.group(3):
            k["words"][int(m.group(3))] = text
        else:
            k[int(m.group(2))] = text
    out = []
    for n, block in questions(qtext).items():
        try:
            out.append(_reading(n, block, keys[n]))
        except (KeyError, ValueError, IndexError, AttributeError) as e:
            note(
                f"interactive_reading {n}{page_of('interactive_reading', f'{n}.1)')}: {e}, skipped"
            )
    return out


def _reading(n: int, q: str, key: dict) -> dict:
    labels: dict[tuple, re.Match] = {}
    for m in re.finditer(rf"(?m)^\s*{n}\.(\d)(?:\.(\d+))?\)", q):
        if (m.group(1), m.group(2)) in labels:
            note(
                f"interactive_reading {n}{page_of('interactive_reading', f'{n}.1)')}: the label "
                f"{n}.{m.group(1)}) is used twice, the parts are found by their titles"
            )
        labels.setdefault((m.group(1), m.group(2)), m)
    heads = {" ".join(m.group(1).lower().split()[:3]): m for m in re.finditer(IR_HEADS, q)}
    stops = [m.start() for m in labels.values()] + [m.start() for m in heads.values()]
    label_stops = [m.start() for m in labels.values()]
    # 1: the first part with numbered gaps, and a list of words for each gap
    passage_q = _segment(q, heads["complete the sentences"].end(), stops)
    chunks = re.split(r"\(\d+\)", passage_q)
    gaps = len(chunks) - 1
    choices = [
        [clean(w) for w in _segment(q, labels[("1", str(k))].end(), stops).split("/")]
        for k in range(1, gaps + 1)
    ]
    answers = [key["words"][k] for k in range(1, gaps + 1)]
    if len(key["words"]) != gaps:
        raise ValueError(f"{gaps} gaps but {len(key['words'])} answers")
    marked = ""
    for chunk, word, opts in zip(chunks, answers, choices, strict=False):
        right = next((o for o in opts if o.lower() == word.lower()), None)
        if right is None:
            raise ValueError(f"the key word '{word}' is not in its list {opts}")
        marked += chunk + "{" + "|".join([right, *_wrong(right, opts)]) + "}"
    marked = clean(marked + chunks[-1])
    filled = re.sub(r"\{([^{}|]*)\|[^{}]*\}", r"\1", marked)
    # 2: the missing sentence
    _, opts = options(_segment(q, labels[("2", None)].end(), stops))
    missing = _choice(opts, re.sub(r"^\(([a-f])\)", r"\1)", key[2]))
    # The whole text: in 'Highlight the Answer', else 'Complete the Passage'
    full = ""
    if "highlight the answer" in heads:
        full = clean(_segment(q, heads["highlight the answer"].end(), stops))
    stream, where = _alnum(full)
    at = stream.find(_alnum(missing["answer"])[0])
    if at >= 0:
        cut = where[at + len(_alnum(missing["answer"])[0]) - 1] + 1
        rest = full[cut:].lstrip(" .,;:!?”’\")'").strip()
        if not stream.startswith(_alnum(filled)[0]):
            note(
                f"interactive_reading {n}{page_of('interactive_reading', f'{n}.1)')}: Complete the "
                "Passage rewords the first part. The passage keeps the words of Complete the "
                "Sentences, 'rest' comes from Highlight the Answer"
            )
    else:
        cp = clean(_segment(q, heads["complete the passage"].end(), stops))
        stream, where = _alnum(cp)
        start = len(_alnum(filled)[0])
        if not stream.startswith(_alnum(filled)[0]):
            raise ValueError("cannot find the second part of the text")
        rest = cp[where[start - 1] + 1 :].lstrip(" .").lstrip("_ ").strip()
        note(f"interactive_reading {n}: the whole text has no missing sentence, rest from part 2")
    # 3 and 4: highlight. 5: main idea. 6: title.
    full_text = " ".join([filled, missing["answer"], rest])
    highlights = []
    for k in (3, 4):
        question = clean(_no_heads(_segment(q, labels[(str(k), None)].end(), stops)))
        answer = _highlight(full_text, key[k].rstrip(" ."))
        if answer is None:
            raise ValueError(f"highlight {k}: '{key[k]}' is not in the text")
        if answer != key[k].rstrip(" ."):
            note(
                f"interactive_reading {n}.{k}{page_of('interactive_reading', f'{n}.{k})')}: "
                f"the key highlight '{key[k]}' is not in the text, the bank uses '{answer}'"
            )
        highlights.append({"question": question, "answer": answer})
    # 'Identify the Idea' and 'Title the Passage' start a part, else the labels 5) and 6)
    idea_at = heads["identify the idea"].end() if "identify the idea" in heads else None
    title_at = heads["title the passage"].end() if "title the passage" in heads else None
    idea_at = idea_at or labels[("5", None)].end()
    title_at = title_at or labels[("6", None)].end()
    idea_text = _no_heads(
        q[idea_at : heads["title the passage"].start()]
        if "title the passage" in heads
        else _segment(q, idea_at, label_stops)
    )
    title_text = _no_heads(q[title_at:])
    _, idea = options(idea_text)
    _, title = options(title_text)
    return {
        "n": n,
        "passage": marked,
        "missing_sentence": missing,
        "rest": rest,
        "highlight": highlights,
        "main_idea": _choice(idea, re.sub(r"^\(([a-f])\)", r"\1)", key[5])),
        "best_title": _choice(title, re.sub(r"^\(([a-f])\)", r"\1)", key[6])),
    }


# ---------- Interactive Listening ----------

SPEAKER = re.compile(r"(?m)^\s*(?:(\d+)\.2\.(\d+)\)\s*)?([A-Z][a-z]+):[ \t]*")
PARTNERS = {"Professor": "professor", "Classmate": "student", "Student": "student"}


def _answer(stem: str, key: str, label: str) -> str:
    """The words of the key sentence that fill the ___ of the stem."""
    before, _, after = stem.partition("___")
    tok = re.compile(r"[A-Za-z0-9’']+")
    b = [m.group(0).lower() for m in tok.finditer(before)]
    f = [m.group(0).lower() for m in tok.finditer(after)]
    kw = list(tok.finditer(key))
    k = [m.group(0).lower() for m in kw]
    q = [*b, "\0", *f]
    same: dict[int, int] = {}
    for blk in difflib.SequenceMatcher(None, q, k, autojunk=False).get_matching_blocks():
        same |= {blk.a + i: blk.b + i for i in range(blk.size)}
    lo = max([same[i] + 1 for i in same if i < len(b)] + [0])
    hi = min([same[i] for i in same if i > len(b)] + [len(k)])
    if hi <= lo:
        return ""
    if sum(i in same for i in range(len(q))) < len(b) + len(f):
        note(f"{label}: the key '{key}' rewords the sentence '{stem}', check the answer")
    return key[kw[lo].start() : kw[hi - 1].end()]


def _place_gap(stem: str, key: str) -> str:
    """Put ___ where the key sentence has words that the stem has not."""
    tok = re.compile(r"[A-Za-z0-9’']+")
    sw = list(tok.finditer(stem))
    kw = [m.group(0).lower() for m in tok.finditer(key)]
    ops = difflib.SequenceMatcher(None, [m.group(0).lower() for m in sw], kw).get_opcodes()
    inserts = [o for o in ops if o[0] == "insert"]
    if len(inserts) != 1:
        return stem
    at = inserts[0][1]
    pos = sw[at].start() if at < len(sw) else len(stem.rstrip(".?! "))
    return (
        (stem[:pos] + "___ " + stem[pos:]).strip()
        if at < len(sw)
        else stem[:pos] + " ___" + stem[pos:]
    )


def _stem(text: str) -> str:
    """A Listen and Complete sentence with ___ for the gap.

    Volume 5 draws the gap with underscores. Volume 4 draws a line, which the text has
    as a run of spaces."""
    text = text.strip()
    text = re.sub(r"_{3,}", "\0", text)
    if "\0" not in text:
        text = re.sub(r" {3,}\s*", " \0 ", text, count=1)
    text = clean(text.replace("\0", " ___ ")).replace(" ___ ", " ___ ")
    return re.sub(r"___\s+([.,;:!?])", r"___\1", text)


def interactive_listening(doc, pages: tuple[int, int], qtext: str, key: str, audio: Audio):
    blocks = questions(qtext)
    key_blocks = questions(key)
    urls = _listening_audio(doc, pages)
    out = []
    for n in sorted(blocks):
        try:
            out.append(_listening(n, blocks[n], key_blocks[n], urls.get(n, {}), audio))
        except (KeyError, ValueError) as e:
            note(f"interactive_listening {n}: {e}, skipped")
    return out


def _listening_audio(doc, pages: tuple[int, int]) -> dict[int, dict]:
    """Question -> {'scenario': url, 0: url, 1: url, ...}.

    A number k is the partner turn after your k-th answer (0: the partner starts)."""
    codes = qr_codes(doc, *pages)
    labels = words(doc, *pages, r"Question \d+|\d+\.\d\)|\d+\.2\.\d+\)")
    events = sorted(
        [(p, r.y0, "label", t) for p, r, t in labels] + [(p, y, "qr", u) for p, _, y, u in codes]
    )
    out: dict[int, dict] = {}
    n, where = None, None
    for _, _, kind, text in events:
        if kind == "label":
            if text.startswith("Question"):
                n, where = int(text.split()[1]), "scenario"
            else:
                parts_ = text[:-1].split(".")
                n = int(parts_[0])
                if parts_[1] == "1":
                    where = "scenario"
                elif parts_[1] == "2":
                    where = int(parts_[2]) if len(parts_) == 3 else 0
                else:
                    where = None
            continue
        if n is None or where is None:
            note(f"interactive_listening: QR code {text} is outside a question")
            continue
        got = out.setdefault(n, {})
        if where == "scenario" and where in got:
            # Question 3 of Volume 5 has no '3.2)' label: the partner starts the talk.
            where = 0
        if where in got:
            note(f"interactive_listening {n}: two QR codes for turn {where}, the first is kept")
            continue
        got[where] = text
    return out


def _complete_parts(n: int, q: str, marks: list, stops: list[int]) -> list[tuple[int, str]]:
    """(k, text) of each Listen and Complete item: a question, then the sentence."""
    out = [
        (int(m.group(2)), _segment(q, m.end(), stops))
        for m in marks
        if m.group(1) == "1" and m.group(2)
    ]
    if out:
        return out
    # Some questions have no 'n.1.k)' labels: a line that ends with '?' starts an item.
    head = next((m for m in marks if m.group(1) == "1"), None)
    if head is None:
        return []
    text = _segment(q, head.end(), stops)
    text = re.sub(r"(?m)^\s*(Listen and Complete|Listen to the scenario.*)\s*$", "", text)
    for line in text.splitlines():
        if line.strip().endswith("?"):
            out.append((len(out) + 1, line))
        elif out:
            out[-1] = (out[-1][0], out[-1][1] + "\n" + line)
    note(
        f"interactive_listening {n}{page_of('interactive_listening', f'{n}.1) Listen')}: "
        "Listen and Complete has no 'n.1.k)' labels, the items were split at the questions"
    )
    return out


def photos(doc, first: int, last: int, out_dir: Path, kind: str) -> dict[int, str]:
    """Save each photo as <kind>-<n>.jpg. The '12)' label left of a photo gives n."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = {}
    for n in range(first, last + 1):
        page = doc[n - 1]
        found = [
            (int(w[4][:-1]), fitz.Rect(w[:4]))
            for w in page.get_text("words")
            if re.fullmatch(r"\d+\)", w[4])
        ]
        for info in page.get_image_info(xrefs=True):
            box = fitz.Rect(info["bbox"])
            cy = (box.y0 + box.y1) / 2
            inside = [
                num
                for num, r in found
                if abs((r.y0 + r.y1) / 2 - cy) < 20 and 0 <= box.x0 - r.x1 < 40
            ]
            if not info["xref"] or len(inside) != 1:
                if info["xref"] and found:
                    note(f"{kind} page {n}: a photo without one label {inside}, skipped")
                continue
            if inside[0] in saved:
                note(f"{kind} page {n}: two photos for {inside[0]}")
            pix = fitz.Pixmap(doc, info["xref"])
            if pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            if pix.alpha:
                pix = fitz.Pixmap(pix, 0)
            name = f"{kind}-{inside[0]:02d}.jpg"
            pix.save(out_dir / name, jpg_quality=92)
            saved[inside[0]] = name
    return saved


def _listening(n: int, q: str, key: str, urls: dict, audio: Audio) -> dict:
    # The key: the scenario, the Listen and Complete answers, then the conversation.
    first_turn = SPEAKER.search(key, key.find(f"{n}.1.1)"))
    lc_key = key[: first_turn.start()] if first_turn else key
    scenario_key = re.split(rf"(?m)^\s*{n}\.1\.1\)", lc_key)[0]
    scenario = clean(
        re.sub(rf"(?m)^\s*({n}\.1\)\s*Listen and Complete|Scenario:)", "", scenario_key)
    )
    complete_key = {
        int(m.group(1)): m.group(2)
        for m in re.finditer(
            rf"(?ms)^\s*{n}\.1\.(\d+)\)\s*(.*?)(?=^\s*{n}\.\d(?:\.\d+)?\)|\Z)", lc_key
        )
    }
    # The questions: Listen and Complete, then the options for each of your turns.
    marks = list(re.finditer(rf"(?m)^\s*{n}\.(\d)(?:\.(\d+))?\)", q))
    stops = [m.start() for m in marks] + [m.start() for m in SPEAKER.finditer(q)]
    complete = []
    for k, seg in _complete_parts(n, q, marks, stops):
        question, mark, stem = seg.partition("?")
        if not mark:
            question, stem = "", seg
        question = clean(question + mark)
        ans_text = clean(complete_key.get(k, ""))
        if "?" in ans_text:  # Volume 5 repeats the question in the key
            ans_text = ans_text.split("?", 1)[1].strip()
        sentence = _stem(stem)
        if "___" not in sentence:
            sentence = _place_gap(sentence, ans_text)
            page = page_of("interactive_listening", f"{n}.1.{k})")
            note(
                f"interactive_listening {n}.1.{k}{page}: the sentence shows no gap, "
                f"it was placed from the key: '{sentence}'"
            )
        label = f"interactive_listening {n}.1.{k}"
        answer = _answer(
            sentence, ans_text, label + page_of("interactive_listening", f"{n}.1.{k})")
        )
        if sentence.count("___") != 1 or not answer:
            note(f"interactive_listening {n}.1.{k}: cannot read the gap of '{sentence}'")
            continue
        item = {"question": question, "sentence": sentence, "answer": answer}
        if not question:
            del item["question"]
        complete.append(item)
    if len(complete_key) != len(complete):
        note(f"interactive_listening {n}: {len(complete_key)} complete answers in the key")
    # The conversation in the key
    turns_key = [t for t in SPEAKER.finditer(key) if t.start() >= len(lc_key)]
    turns, partner, mine = [], None, 0
    for i, m in enumerate(turns_key):
        end = turns_key[i + 1].start() if i + 1 < len(turns_key) else len(key)
        text = clean(key[m.end() : end])
        who = m.group(3)
        if who == "You":
            mine += 1
            seg = next((x for x in marks if x.group(1) == "2" and x.group(2) == str(mine)), None)
            if seg is None:
                raise ValueError(f"no options for your turn {mine}")
            _, opts = options(_segment(q, seg.end(), stops))
            choice = re.sub(r"^\(([a-f])\)", r"\1)", text)
            letter = re.match(r"([a-f])\)", choice)
            picked = _choice(opts, choice)
            if letter and opts.get(letter.group(1)) != picked["answer"]:
                note(
                    f"interactive_listening {n}.2.{mine}"
                    f"{page_of('interactive_listening', f'{n}.2.{mine})')}: the key gives letter "
                    f"{letter.group(1)}) but the text of another option, the text decides"
                )
            turns.append({"you": picked})
        elif who in PARTNERS:
            partner = partner or PARTNERS[who]
            turn = {"partner": text}
            if mine in urls:
                name = audio.get(urls.pop(mine), f"listening-{n:02d}-{len(turns) + 1:02d}.mp3")
                if name:
                    turn["audio"] = name
            else:
                note(
                    f"interactive_listening {n}: no audio for the partner turn after your turn "
                    f"{mine}"
                )
            turns.append(turn)
        else:
            raise ValueError(f"unknown speaker '{who}'")
    item = {"n": n, "partner": partner or "student", "scenario": scenario}
    if "scenario" in urls:
        name = audio.get(urls.pop("scenario"), f"listening-{n:02d}-scenario.mp3")
        if name:
            item["scenario_audio"] = name
    else:
        note(f"interactive_listening {n}: no scenario audio")
    for k, url in urls.items():
        note(f"interactive_listening {n}: QR code for turn {k} has no partner turn: {url}")
    item["complete"] = complete
    item["conversation"] = turns
    return item


# ---------- speaking and writing ----------


def interactive_speaking(doc, pages: tuple[int, int], key: str, audio: Audio) -> list[dict]:
    codes = qr_codes(doc, *pages)
    labels, current = [], 0
    for p, r, t in words(doc, *pages, r"Question \d+|\d+\)"):
        if t.startswith("Question"):
            current = int(t.split()[1])
        else:
            labels.append((p, r, (current, int(t[:-1]))))
    urls = beside(labels, codes)
    out = []
    for n, block in questions(key).items():
        items = [(int(m.group(1)), m) for m in re.finditer(rf"(?m)^\s*(?:{n}\.)?(\d+)\)\s*", block)]
        texts = []
        for i, (k, m) in enumerate(items):
            end = items[i + 1][1].start() if i + 1 < len(items) else len(block)
            texts.append((k, clean(block[m.end() : end])))
        topics: list[dict] = []
        for k, text in texts:
            about = re.search(r"questions about (.+?)\.", text)
            if about or not topics:
                topics.append({"topic": about.group(1) if about else "", "questions": []})
            question = {"text": text}
            if (n, k) in urls:
                name = audio.get(urls.pop((n, k)), f"speaking-{n:02d}-{k:02d}.mp3")
                if name:
                    question["audio"] = name
            else:
                note(f"interactive_speaking {n}.{k}: no QR code")
            topics[-1]["questions"].append(question)
        out.append({"n": n, "topics": topics})
    for (n, k), url in urls.items():
        note(f"interactive_speaking: QR code {n}.{k} has no transcript: {url}")
    return out


def interactive_writing(qtext: str) -> list[dict]:
    out = []
    for n, block in questions(qtext).items():
        m = re.search(r"Step 1:(.*?)Step 2:(.*)", block, re.S)
        if not m:
            note(f"interactive_writing {n}: no Step 1 and Step 2, skipped")
            continue
        follow = [clean(x) for x in m.group(2).split("•") if clean(x)]
        out.append({"n": n, "prompt": clean(m.group(1)), "follow_ups": follow})
    return out


def prompts(qtext: str, bullets: bool = False) -> list[dict]:
    out = []
    for n, t in numbered(qtext):
        prompt, *rest = t.split("•")
        item = {"n": n, "prompt": clean(prompt)}
        if bullets and rest:
            item["bullets"] = [clean(x) for x in rest if clean(x)]
        elif rest:
            note(f"prompt {n}: has bullets, they are kept in the prompt")
            item["prompt"] = clean(t.replace("•", " "))
        out.append(item)
    return out


# ---------- checks ----------


def check(bank: dict) -> None:
    """Run det-coach's own checks on the items, if det-coach is installed."""
    try:
        from detcoach import content
    except ImportError:
        print("detcoach is not installed: the checks of det-coach were not run")
        return
    for kind, wrap in (
        ("read_complete", lambda i: i),
        ("interactive_reading", lambda i: i),
        ("interactive_listening", lambda i: i),
        ("fill_blanks", lambda i: {"sentences": [i["sentence"]]}),
    ):
        for item in bank[kind]:
            for p in content.CHECKS[kind](wrap(item)):
                note(f"det-coach check: {kind} {item['n']}: {p}")


def main(pdf: Path, out: Path) -> None:
    doc = fitz.open(pdf)
    pages, answers = parts(doc)
    RANGES.update(pages)
    PAGES.update({i + 1: clean(norm(p.get_text())) for i, p in enumerate(doc)})
    key = answer_key(doc, *answers)
    q = {k: page_text(doc, *v) for k, v in pages.items()}
    audio = Audio(out)
    rc_text = "\n".join(
        x for x in line_text(doc, *pages["read_complete"]).splitlines() if not NOISE.match(x)
    )
    bank: dict[str, list] = {
        "read_select": read_select(q["read_select"], key["read_select"]),
        "fill_blanks": fill_blanks(q["fill_blanks"], key["fill_blanks"]),
        "read_complete": read_complete(rc_text, key["read_complete"]),
        "listen_type": listen_type(doc, pages["listen_type"], key["listen_type"], audio),
        "interactive_reading": interactive_reading(
            q["interactive_reading"], key["interactive_reading"]
        ),
        "interactive_listening": interactive_listening(
            doc,
            pages["interactive_listening"],
            q["interactive_listening"],
            key["interactive_listening"],
            audio,
        ),
        "interactive_writing": interactive_writing(q["interactive_writing"]),
        "read_then_speak": prompts(q["read_then_speak"], bullets=True),
        "interactive_speaking": interactive_speaking(
            doc, pages["interactive_speaking"], key["interactive_speaking"], audio
        ),
        "writing_sample": prompts(q["writing_sample"]),
        "speaking_sample": prompts(q["speaking_sample"]),
    }
    for kind in ("write_photo", "speak_photo"):
        saved = photos(doc, *pages[kind], out / "photos", kind.replace("_", "-"))
        bank[kind] = [{"n": n, "photo": name} for n, name in sorted(saved.items())]
    check(bank)
    bank["notes"] = notes
    out.mkdir(parents=True, exist_ok=True)
    (out / "bank.json").write_text(json.dumps(bank, indent=1, ensure_ascii=False) + "\n")
    print()
    for kind, items in bank.items():
        if kind == "notes":
            continue
        extra = ""
        if kind == "listen_type":
            extra = f", {sum('audio' in i for i in items)} with audio"
        if kind == "interactive_listening":
            turns = [t for i in items for t in i["conversation"] if "partner" in t]
            extra = (
                f", {sum('scenario_audio' in i for i in items)} scenario audio, "
                f"{sum('audio' in t for t in turns)} of {len(turns)} partner turns with audio, "
                f"{sum(len(i['complete']) for i in items)} complete sentences"
            )
        if kind == "interactive_speaking":
            qs = [x for i in items for t in i["topics"] for x in t["questions"]]
            extra = f", {len(qs)} questions, {sum('audio' in x for x in qs)} with audio"
        print(f"{kind}: {len(items)}{extra}")
    print(f"audio: {audio.saved} files, {len(audio.failed)} failed")
    print(f"notes: {len(notes)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
