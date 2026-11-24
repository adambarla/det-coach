import json

import pytest
from conftest import REPO, write_round

from detcoach import speech
from detcoach.rounds import OFFICIAL, RoundError, list_rounds, load_round, repeats
from detcoach.tasks import TASK_TYPES

# Rounds that ship with the repository. Rounds from the official booklet stay local.
SHIPPED_TYPES = set(TASK_TYPES) - {"listen_then_speak"}


def test_shipped_rounds_are_valid():
    rounds = [r for r in list_rounds(REPO / "rounds") if not r.id.startswith(OFFICIAL)]
    assert len(rounds) >= 3
    # Together the shipped rounds use every 2026 task type, and at least one is a full test.
    assert {s.type for r in rounds for s in r.steps} == SHIPPED_TYPES
    assert any({s.type for s in r.steps} == SHIPPED_TYPES for r in rounds)


def test_steps_take_times_from_task_types(root):
    r = load_round(root / "rounds" / "round-x")
    assert [s.id for s in r.steps] == ["photo-1", "iw-1", "iw-2", "read-speak"]
    iw1, iw2 = r.steps[1], r.steps[2]
    assert (iw1.prep, iw1.answer) == (30, 300)
    assert (iw2.prep, iw2.answer, iw2.show_previous) == (0, 180, "iw-1")
    assert r.steps[0].photo == "/rounds/round-x/photos/p.jpg"


def test_interactive_speaking_has_one_step_per_question(tmp_path):
    topics = [{"topic": "a", "questions": ["q1", "q2"]}, {"topic": "b", "questions": ["q3"]}]
    write_round(tmp_path, tasks=[{"id": "talk", "type": "interactive_speaking", "topics": topics}])
    steps = load_round(tmp_path / "rounds" / "round-x").steps
    assert [s.id for s in steps] == ["talk-1", "talk-2", "talk-3"]
    assert steps[2].part == "Question 3 of 3"
    assert steps[2].listen[0].text == "q3"


@pytest.mark.parametrize(
    "task, problem",
    [
        ({"id": "a", "type": "nope"}, "unknown type"),
        ({"id": "Bad Id", "type": "writing_sample", "prompt": "x"}, "'id' must be"),
        ({"id": "a", "type": "writing_sample"}, "needs a non-empty 'prompt'"),
        ({"id": "a", "type": "write_photo", "photo": "missing.jpg"}, "is missing"),
        ({"id": "a", "type": "summarize_conversation", "conversation": []}, "at least 4 lines"),
    ],
)
def test_invalid_tasks_are_reported(tmp_path, task, problem):
    write_round(tmp_path, tasks=[task])
    with pytest.raises(RoundError) as e:
        load_round(tmp_path / "rounds" / "round-x")
    assert any(problem in p for p in e.value.problems)


def test_round_id_must_match_folder(tmp_path):
    folder = write_round(tmp_path)
    data = json.loads((folder / "round.json").read_text())
    data["id"] = "other"
    (folder / "round.json").write_text(json.dumps(data))
    with pytest.raises(RoundError, match="folder name"):
        load_round(folder)


def test_invalid_rounds_are_skipped(root):
    (root / "rounds" / "round-y").mkdir()
    (root / "rounds" / "round-y" / "round.json").write_text("{")
    assert [r.id for r in list_rounds(root / "rounds")] == ["round-x"]


def test_steps_know_their_section(root):
    r = load_round(root / "rounds" / "round-x")
    assert [s.section for s in r.steps] == ["writing", "writing", "writing", "speaking"]
    assert r.summary()["sections"] == {
        "writing": {"steps": 3, "minutes": 10},
        "speaking": {"steps": 1, "minutes": 2},
    }


def test_interactive_listening_summary_stays_in_listening():
    r = load_round(REPO / "rounds" / "round-03")
    summary = next(s for s in r.steps if s.id == "listening-1-summary")
    assert (summary.skill, summary.section) == ("writing", "listening")


def test_listen_and_complete_questions_are_optional():
    new = next(s for s in load_round(REPO / "rounds" / "round-04").steps if s.id == "listening-1")
    old = next(s for s in load_round(REPO / "rounds" / "round-03").steps if s.id == "listening-1")
    assert new.data["questions"][0] == "What do you want to ask students about?"
    assert set(old.data["questions"]) == {""}


def test_shipped_rounds_do_not_repeat_content():
    assert repeats(REPO / "rounds") == []


def test_repeats_are_found(tmp_path):
    task = {"id": "ws", "type": "writing_sample", "prompt": "Is homework useful?"}
    write_round(tmp_path, "round-a", tasks=[task])
    write_round(tmp_path, "round-b", tasks=[{**task, "prompt": "Is  HOMEWORK useful"}])
    found = repeats(tmp_path / "rounds")  # the prompt, and the photo that both test rounds share
    assert [f.split(" ")[1] for f in found] == ["photo", "prompt"]
    assert all(f.startswith("round-b:") and f.endswith("already in round-a") for f in found)


def recorded_round(tmp_path, tasks):
    folder = write_round(tmp_path, tasks=tasks)
    (folder / "audio").mkdir()
    (folder / "audio" / "a.mp3").write_bytes(b"ID3")
    return load_round(folder)


def test_recorded_audio_is_played_instead_of_a_voice(tmp_path):
    sentences = [{"text": "The bus is late.", "audio": "a.mp3"}, "It rains."]
    lts = {"id": "lts", "type": "listen_then_speak", "text": "Why?", "audio": "a.mp3"}
    r = recorded_round(tmp_path, [{"id": "d", "type": "listen_type", "sentences": sentences}, lts])
    d1, d2, step = r.steps
    assert (d1.listen[0].text, d1.listen[0].audio, d2.listen[0].audio) == (
        "The bus is late.",
        "a.mp3",
        "",
    )
    assert step.listen[0].text == "Why?"
    assert speech.audio_path(tmp_path, r, step.id) == r.path / "audio" / "a.mp3"


def test_missing_recordings_are_reported(tmp_path):
    task = {"id": "lts", "type": "listen_then_speak", "text": "Why?", "audio": "gone.mp3"}
    with pytest.raises(RoundError) as e:
        recorded_round(tmp_path, [task])
    assert any("gone.mp3" in p for p in e.value.problems)


def test_interactive_listening_can_skip_listen_and_complete(tmp_path):
    shipped = json.loads((REPO / "rounds" / "round-04" / "round.json").read_text())
    task = next(t for t in shipped["tasks"] if t["type"] == "interactive_listening")
    task = {k: v for k, v in task.items() if k != "complete"}
    step = load_round(write_round(tmp_path, tasks=[task])).steps[0]
    assert step.part == "Listen and Respond"
    assert step.data.get("complete", []) == []


def test_official_rounds_are_not_checked_for_repeats(tmp_path):
    task = {"id": "ws", "type": "writing_sample", "prompt": "Is homework useful?"}
    write_round(tmp_path, "round-a", tasks=[task])
    write_round(tmp_path, "official-01", tasks=[task])
    assert repeats(tmp_path / "rounds") == []
