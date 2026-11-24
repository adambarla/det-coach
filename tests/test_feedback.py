import copy

from conftest import write_round

from detcoach import feedback
from detcoach.attempts import Attempts
from detcoach.rounds import load_round


def make_attempt(root):
    attempts = Attempts(root / "attempts")
    aid = attempts.create("round-x")
    attempts.save(aid, "photo-1", b"A man sell pickles.", "text/plain", True, 60)
    attempts.save(aid, "read-speak", b"\x1aE\xdf\xa3", "audio/webm", True, 80)
    attempts.finish(aid)
    return attempts, aid


TRANSCRIPTS = {
    "read-speak": {
        "text": "I explained it.",
        "words": [
            {"word": "I", "start": 0.5, "end": 0.6},
            {"word": "explained", "start": 2.0, "end": 2.5},
            {"word": "it.", "start": 2.6, "end": 2.8},
        ],
        "metrics": {"words": 3},
    }
}

GOOD = {
    "version": 1,
    "grader": "test",
    "summary": "Fine.",
    "estimate": {"writing": [100, 110], "speaking": [90, 100]},
    "priorities": [{"title": "Use the present continuous", "detail": "In photo answers."}],
    "steps": {
        "photo-1": {
            "band": [100, 110],
            "criteria": {c: {"band": [100, 110], "note": "ok"} for c in feedback.WRITING_CRITERIA},
            "fixes": [{"original": "a man sell", "better": "a man is selling", "why": "tense"}],
        },
        "read-speak": {
            "band": [90, 100],
            "criteria": {
                **{c: {"band": [90, 100], "note": "ok"} for c in feedback.WRITING_CRITERIA},
                "fluency": {"band": [80, 90], "note": "slow"},
                "pronunciation": None,
            },
        },
    },
}


def test_packet_has_answers_transcripts_and_hidden_steps(root):
    attempts, aid = make_attempt(root)
    rnd = load_round(root / "rounds" / "round-x")
    text = feedback.build_packet(rnd, attempts.path(aid), attempts.manifest(aid), TRANSCRIPTS)
    assert "A man sell pickles." in text
    assert "I [1.4 s] explained it." in text
    assert "`iw-1`" in text and "Not answered" in text
    assert str(root / "rounds" / "round-x" / "photos" / "p.jpg") in text


def test_valid_feedback_passes(root):
    attempts, aid = make_attempt(root)
    rnd = load_round(root / "rounds" / "round-x")
    assert feedback.check({**GOOD, "attempt": aid}, rnd, attempts.manifest(aid)) == []


def test_invalid_feedback_lists_every_problem(root):
    attempts, aid = make_attempt(root)
    rnd = load_round(root / "rounds" / "round-x")
    bad = copy.deepcopy({**GOOD, "attempt": aid})
    bad["estimate"]["writing"] = [103, 110]
    del bad["steps"]["read-speak"]
    bad["steps"]["photo-1"]["criteria"]["fluency"] = {"band": [100, 100], "note": "x"}
    bad["steps"]["photo-1"]["fixes"][0].pop("why")
    problems = feedback.check(bad, rnd, attempts.manifest(aid))
    assert len(problems) == 4
    assert any("estimate.writing" in p for p in problems)
    assert any("'read-speak' has no feedback" in p for p in problems)
    assert any("not a writing criterion" in p for p in problems)
    assert any("fixes[0]" in p for p in problems)


def test_latest_skips_unfinished_attempts(root):
    attempts, aid = make_attempt(root)
    assert attempts.resolve("latest") == aid
    assert attempts.status(aid) == "awaiting_feedback"


def test_speaking_steps_need_every_speaking_criterion(root):
    attempts, aid = make_attempt(root)
    rnd = load_round(root / "rounds" / "round-x")
    bad = copy.deepcopy({**GOOD, "attempt": aid})
    del bad["steps"]["read-speak"]["criteria"]["pronunciation"]
    bad["steps"]["photo-1"]["criteria"]["grammar"] = "good"
    problems = feedback.check(bad, rnd, attempts.manifest(aid))
    assert any("'pronunciation' is missing" in p for p in problems)
    assert any("criteria.grammar must be an object" in p for p in problems)


def test_latest_is_the_newest_by_start_time(root):
    write_round(root, "round-a")
    attempts, older = make_attempt(root)
    newer = attempts.create("round-a")
    attempts.finish(newer)
    for aid, started in ((older, "2026-01-02T10:00:00"), (newer, "2026-01-03T10:00:00")):
        m = attempts.manifest(aid)
        attempts._write(aid, {**m, "started": started})
    assert attempts.resolve("latest") == newer


def test_packet_shows_unsubmitted_drafts(root):
    attempts, aid = make_attempt(root)
    attempts.save(aid, "iw-1", b"Half an answer", "text/plain", False)
    rnd = load_round(root / "rounds" / "round-x")
    text = feedback.build_packet(rnd, attempts.path(aid), attempts.manifest(aid), {})
    assert "Half an answer" in text and "Not submitted" in text
