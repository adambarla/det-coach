import json

import pytest
from conftest import REPO, write_round

from detcoach import bank, speech
from detcoach.attempts import Attempts
from detcoach.rounds import load_round, round_dir

WORDS = [{"word": f"word{n}", "real": n % 2 == 0} for n in range(20)]


def make(tmp_path, round_id, kind, tasks):
    folder = write_round(tmp_path, round_id, tasks=tasks)
    data = json.loads((folder / "round.json").read_text())
    (folder / "round.json").write_text(json.dumps({**data, "kind": kind}))
    return folder


def answer(root, round_id, step_ids):
    attempts = Attempts(root / "attempts")
    aid = attempts.create(round_id)
    for sid in step_ids:
        attempts.save(aid, sid, b'{"real": true}', "application/json", True, 3)
    return aid


@pytest.fixture
def root(tmp_path):
    make(tmp_path, "pool", "pool", [{"id": "select", "type": "read_select", "words": WORDS[:10]}])
    make(tmp_path, "test-a", "test", [{"id": "select", "type": "read_select", "words": WORDS[10:]}])
    return tmp_path


def test_drills_skip_the_questions_of_tests_not_taken(root):
    rnd = load_round(round_dir(root, bank.make_drill(root, "read_select")))
    assert rnd.kind == "drill"
    assert len(rnd.steps) == 10  # the pool has 10 words; the test keeps its 10
    assert all(v.startswith("pool/select#") for v in rnd.origin.values())


def test_answered_test_questions_join_the_drills(root):
    answer(root, "test-a", ["select-1", "select-2"])
    rnd = load_round(round_dir(root, bank.make_drill(root, "read_select")))
    assert len(rnd.steps) == 12
    # Questions not seen yet come first, then the ones seen longest ago.
    assert {rnd.origin[f"select#{n}"] for n in (11, 12)} == {"test-a/select#1", "test-a/select#2"}


def test_drill_answers_count_for_the_original_question(root):
    rid = bank.make_drill(root, "read_select")
    rnd = load_round(round_dir(root, rid))
    answer(root, rid, ["select-1"])
    done = bank.history(root)
    assert [a.key for a in done] == [rnd.origin["select#1"]]
    row = next(r for r in bank.progress(root) if r["type"] == "read_select")
    assert (row["done"], row["fresh"], row["held"]) == (1, 9, 10)
    assert row["share"] == (1.0 if WORDS[int(done[0].key.split("#")[1]) - 1]["real"] else 0.0)


def test_photos_are_copied_with_their_credits(tmp_path):
    make(tmp_path, "pool", "pool", [{"id": "p", "type": "write_photo", "photo": "p.jpg"}])
    rnd = load_round(round_dir(tmp_path, bank.make_drill(tmp_path, "write_photo")))
    assert rnd.photos == {
        "pool-p.jpg": json.loads((tmp_path / "rounds/pool/round.json").read_text())["photos"][
            "p.jpg"
        ]
    }
    assert (rnd.path / "photos" / "pool-p.jpg").is_file()


def test_summary_drills_use_interactive_listening_conversations(tmp_path):
    shipped = json.loads((REPO / "rounds" / "round-04" / "round.json").read_text())
    il = next(t for t in shipped["tasks"] if t["type"] == "interactive_listening")
    make(tmp_path, "pool", "pool", [il])
    rnd = load_round(round_dir(tmp_path, bank.make_drill(tmp_path, "summarize_conversation")))
    (step,) = rnd.steps
    assert step.type == "summarize_conversation"
    assert step.listen[0].voice == il["partner"] or step.listen[0].voice == "student"


def test_interactive_speaking_questions_map_to_topics(tmp_path):
    topics = [{"topic": "a", "questions": ["q1", "q2"]}, {"topic": "b", "questions": ["q3"]}]
    folder = make(
        tmp_path, "pool", "pool", [{"id": "talk", "type": "interactive_speaking", "topics": topics}]
    )
    rnd = load_round(folder)
    assert [bank.step_item(rnd, s) for s in rnd.steps] == [
        "pool/talk#1",
        "pool/talk#1",
        "pool/talk#2",
    ]


def test_no_questions_is_an_error(root):
    with pytest.raises(LookupError):
        bank.make_drill(root, "writing_sample")
    with pytest.raises(ValueError):
        bank.make_drill(root, "listen_then_speak")


def test_recordings_of_speaking_and_listening_follow_the_question(tmp_path):
    q = [{"text": "Do you cook?", "audio": "q1.mp3"}, "Why?"]
    folder = make(
        tmp_path,
        "pool",
        "pool",
        [
            {
                "id": "talk",
                "type": "interactive_speaking",
                "topics": [{"topic": "Food", "questions": q}],
            }
        ],
    )
    (folder / "audio").mkdir()
    (folder / "audio" / "q1.mp3").write_bytes(b"ID3")
    rnd = load_round(round_dir(tmp_path, bank.make_drill(tmp_path, "interactive_speaking")))
    assert rnd.steps[0].listen[0].audio == "pool-q1.mp3"
    assert speech.audio_path(tmp_path, rnd, rnd.steps[0].id) == rnd.path / "audio" / "pool-q1.mp3"
    assert rnd.steps[1].listen[0].audio == ""


def test_official_rounds_replace_the_others(root):
    make(root, "official-x", "pool", [{"id": "select", "type": "read_select", "words": WORDS[:4]}])
    answer(root, "test-a", ["select-1"])
    rnd = load_round(round_dir(root, bank.make_drill(root, "read_select")))
    assert all(v.startswith("official-x/") for v in rnd.origin.values())
    row = next(r for r in bank.progress(root) if r["type"] == "read_select")
    assert (row["done"], row["fresh"], row["held"]) == (0, 4, 0)
