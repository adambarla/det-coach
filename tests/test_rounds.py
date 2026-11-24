import json

import pytest
from conftest import REPO, write_round

from detcoach.rounds import RoundError, list_rounds, load_round
from detcoach.tasks import TASK_TYPES


def test_shipped_rounds_are_valid():
    rounds = list_rounds(REPO / "rounds")
    assert len(rounds) >= 3
    # Together the shipped rounds use every task type, and at least one is a full test.
    assert {s.type for r in rounds for s in r.steps} == set(TASK_TYPES)
    assert any({s.type for s in r.steps} == set(TASK_TYPES) for r in rounds)


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
