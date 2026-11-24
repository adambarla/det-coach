"""Objective measures that the grader uses next to the rubric.

Speaking measures come from word timestamps. The Scoring Guide (2026) ties the top
fluency band to pauses under about 2 seconds at natural places and notes that proficient
speakers often reach about 140 words per minute. These numbers give the grader evidence
that a transcript alone hides.
"""

from __future__ import annotations

import re
from itertools import pairwise

FILLERS = {"um", "umm", "uh", "uhh", "er", "erm", "ah", "eh", "hmm", "mm"}
WORD = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")  # same rule as wordCount in app.js
# Whisper word probability below this often marks a word that was hard to hear.
UNCLEAR_PROB = 0.45


def _norm(w: str) -> str:
    return w.strip().strip(".,!?;:\"'()").lower()


def speaking(words: list[dict], slot_seconds: int) -> dict:
    """words: [{"word", "start", "end", "probability"?}] in order."""
    if not words:
        return {"words": 0, "silent": True, "slot_seconds": slot_seconds}
    fillers = [w for w in words if _norm(w["word"]) in FILLERS]
    content = [w for w in words if _norm(w["word"]) not in FILLERS]
    span = max(words[-1]["end"] - words[0]["start"], 0.001)
    gaps = [b["start"] - a["end"] for a, b in pairwise(words)]
    unclear = [_norm(w["word"]) for w in content if w.get("probability", 1) < UNCLEAR_PROB]
    return {
        "words": len(content),
        "words_per_minute": round(len(content) / span * 60),
        "speaking_seconds": round(span, 1),
        "slot_seconds": slot_seconds,
        "slot_used": round(words[-1]["end"] / slot_seconds, 2),
        "start_delay_seconds": round(words[0]["start"], 1),
        "pauses_over_1s": sum(g >= 1 for g in gaps),
        "pauses_over_2s": sum(g >= 2 for g in gaps),
        "longest_pause_seconds": round(max(gaps, default=0), 1),
        "fillers": len(fillers),
        "unclear_words": unclear[:15],
    }


def writing(text: str) -> dict:
    words = WORD.findall(text)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if WORD.search(s)]
    lower = [w.lower() for w in words]
    return {
        "words": len(words),
        "sentences": len(sentences),
        "words_per_sentence": round(len(words) / len(sentences), 1) if sentences else 0,
        "distinct_word_ratio": round(len(set(lower)) / len(lower), 2) if lower else 0,
        "paragraphs": len([p for p in text.split("\n\n") if p.strip()]),
    }
