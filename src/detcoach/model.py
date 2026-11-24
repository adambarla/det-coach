"""The steps of a round: what one timed screen shows and what it expects."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Line:
    voice: str
    text: str
    audio: str = ""  # a recorded file in the round's audio/ folder, played instead of a voice


@dataclass
class Step:
    id: str
    task: str
    type: str
    name: str
    skill: str
    prep: int
    answer: int
    part: str = ""
    prompt: str = ""
    bullets: list[str] = field(default_factory=list)
    photo: str = ""
    listen: list[Line] = field(default_factory=list)
    show_previous: str = ""
    after: str = ""  # a summary step: the step whose conversation it summarizes (not replayed)
    data: dict = field(default_factory=dict)  # what the screen shows for reading and listening
    key: dict = field(default_factory=dict)  # the correct answers, for scoring
    section: str = ""  # the test section of the task: reading, listening, writing or speaking
