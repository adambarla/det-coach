"""Task types of the test and their official timings.

This module is the single source of truth for prep and answer times. Rounds name a task
type and supply content. They never set times themselves.

Timings follow the DET Question Guide (2026):
https://englishtest-static.duolingo.com/media/resources/Questions%20Guide%202026.pdf
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskType:
    name: str
    skill: str  # "writing" or "speaking"
    prep: int  # seconds to read and plan before the answer starts
    answer: int  # seconds to answer (speaking: the maximum)
    weight: str  # share of the writing or speaking subscore, from the Scoring Guide (2026)
    follow_up_answer: int = 0  # interactive writing only: time for the second question


TASK_TYPES: dict[str, TaskType] = {
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
}
