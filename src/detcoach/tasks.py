"""Task types of the test and their official timings.

This module is the single source of truth for prep and answer times. Rounds name a task
type and supply content. They never set times themselves.

Timings follow the DET Question Guide (2026):
https://englishtest-static.duolingo.com/media/resources/Questions%20Guide%202026.pdf
"""

from __future__ import annotations

from dataclasses import dataclass

SECTIONS = ("reading", "listening", "writing", "speaking")  # the order of the test
GRADED = ("writing", "speaking")  # the agent grades these skills; det-coach scores the rest


@dataclass(frozen=True)
class TaskType:
    name: str
    skill: str  # "reading", "listening", "writing" or "speaking"
    prep: int  # seconds to read and plan before the answer starts
    answer: int  # seconds to answer (speaking: the maximum; sets: per question)
    weight: str  # share of the subscore, from the Scoring Guide (2026)
    follow_up_answer: int = 0  # interactive writing: part 2; interactive listening: summary


ADAPTIVE = "adaptive in the real test, no fixed share"

TASK_TYPES: dict[str, TaskType] = {
    "read_select": TaskType("Read and Select", "reading", 0, 5, f"Reading, {ADAPTIVE}"),
    "fill_blanks": TaskType("Fill in the Blanks", "reading", 0, 20, f"Reading, {ADAPTIVE}"),
    "read_complete": TaskType("Read and Complete", "reading", 0, 180, f"Reading, {ADAPTIVE}"),
    "listen_type": TaskType("Listen and Type", "listening", 0, 60, f"Listening, {ADAPTIVE}"),
    "interactive_reading": TaskType(
        "Interactive Reading", "reading", 0, 480, f"Reading, {ADAPTIVE}"
    ),
    "interactive_listening": TaskType(
        "Interactive Listening", "listening", 0, 390, f"Listening, {ADAPTIVE}", 75
    ),
    "write_photo": TaskType("Write About the Photo", "writing", 0, 60, "33% of Writing (all 3)"),
    "interactive_writing": TaskType(
        "Interactive Writing", "writing", 30, 300, "22% of Writing (both parts)", 180
    ),
    "summarize_conversation": TaskType(
        "Summarize the Conversation", "writing", 0, 75, "22% of Writing (both)"
    ),
    "writing_sample": TaskType("Writing Sample", "writing", 30, 300, "22% of Writing"),
    "speak_photo": TaskType("Speak About the Photo", "speaking", 20, 90, "20% of Speaking"),
    "read_then_speak": TaskType("Read, Then Speak", "speaking", 20, 90, "20% of Speaking"),
    "interactive_speaking": TaskType(
        "Interactive Speaking", "speaking", 0, 35, "40% of Speaking (all questions)"
    ),
    "speaking_sample": TaskType("Speaking Sample", "speaking", 30, 180, "20% of Speaking"),
    # Not in the 2026 test. The official sample booklet (2025) still has it.
    "listen_then_speak": TaskType(
        "Listen, Then Speak", "speaking", 20, 90, "not in the 2026 test (2025 samples)"
    ),
}

# Task types of the current test, in test order. Drills and progress cover these.
RETIRED = {"listen_then_speak"}
DRILLS = tuple(t for t in TASK_TYPES if t not in RETIRED)
