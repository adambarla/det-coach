import json

import pytest
from conftest import REPO, write_round

from detcoach import content, score
from detcoach.rounds import RoundError, load_round

READING = {
    "id": "reading",
    "type": "interactive_reading",
    "passage": "Cats {sleep|swim|sing}. They {hunt|cook|vote} at night. They {purr|bark|moo}.",
    "missing_sentence": {"answer": "Most cats like warm places.", "wrong": ["x.", "y."]},
    "rest": "Some cats sleep in boxes.",
    "highlight": [
        {"question": "When do cats hunt?", "answer": "at night"},
        {"question": "Where do some cats sleep?", "answer": "in boxes"},
    ],
    "main_idea": {"answer": "Cats", "wrong": ["Dogs", "Cows"]},
    "best_title": {"answer": "About Cats", "wrong": ["About Dogs", "About Cows"]},
}


def load(tmp_path, *tasks):
    write_round(tmp_path, tasks=list(tasks))
    return load_round(tmp_path / "rounds" / "round-x")


def test_segments_split_words_and_choices():
    segs, answers = content.segments("I {like} {te|a}.")
    assert segs == ["I ", {"shown": "li", "len": 2}, " ", {"shown": "te", "len": 1}, "."]
    assert answers == ["ke", "a"]
    segs, answers = content.segments("A {b|c|d}.", choices=True, seed="s")
    assert sorted(segs[1]["options"]) == ["b", "c", "d"] and answers == ["b"]


def test_sets_expand_to_one_step_per_item(tmp_path):
    words = [{"word": "cat", "real": True}, {"word": "blorp", "real": False}]
    r = load(
        tmp_path,
        {"id": "select", "type": "read_select", "words": words},
        {"id": "blanks", "type": "fill_blanks", "sentences": ["A {house}.", "The {sun}."]},
    )
    assert [s.id for s in r.steps] == ["select-1", "select-2", "blanks-1", "blanks-2"]
    assert r.steps[1].key == {"real": False} and r.steps[1].answer == 5
    assert r.steps[2].key["missing"] == ["use"] and r.steps[2].answer == 20


def test_interactive_listening_adds_a_summary(tmp_path):
    you = {"you": {"answer": "Yes.", "wrong": ["No.", "Maybe."]}}
    task = {
        "id": "talk",
        "type": "interactive_listening",
        "partner": "professor",
        "scenario": "You ask for help.",
        "complete": [{"sentence": f"Part {i} ___.", "answer": "help"} for i in range(3)],
        "conversation": [{"partner": "Hi."}, *[you] * 5],
    }
    main, summary = load(tmp_path, task).steps
    assert main.answer == 390 and main.key["turns"] == ["Yes."] * 5
    assert main.data["turns"][0] == {"clip": 1}  # clip 0 is the scenario
    assert (summary.id, summary.skill, summary.answer, summary.after) == (
        "talk-summary",
        "writing",
        75,
        "talk",
    )


@pytest.mark.parametrize(
    "task, problem",
    [
        ({"id": "a", "type": "read_select", "words": [{"word": "x", "real": True}]}, "both real"),
        ({"id": "a", "type": "fill_blanks", "sentences": ["No blank."]}, "exactly one"),
        (
            {
                "id": "a",
                "type": "read_complete",
                "title": "T",
                "passage": "A b {c} {d} {e} {f} {g}. H.",
            },
            "start with 5 words",
        ),
        (
            {
                "id": "a",
                "type": "read_complete",
                "title": "T",
                "passage": "A b c d e. {f} {g} {h} {i} {j}.",
            },
            "end with a sentence",
        ),
        ({**READING, "highlight": [{"question": "q", "answer": "not there"}] * 2}, "copied"),
        ({"id": "a", "type": "interactive_listening"}, "'partner' must be"),
    ],
)
def test_invalid_content_is_reported(tmp_path, task, problem):
    with pytest.raises(RoundError) as e:
        load(tmp_path, task)
    assert any(problem in p for p in e.value.problems)


def test_scores_right_wrong_and_partial(tmp_path):
    r = load(
        tmp_path,
        {"id": "blanks", "type": "fill_blanks", "sentences": ["A {house}."]},
        {"id": "dict", "type": "listen_type", "sentences": ["I like tea."]},
        READING,
    )
    blanks, dictation, reading = r.steps
    assert score.score_step(blanks, json.dumps({"missing": ["USE"]}))["credit"] == 1
    assert score.score_step(blanks, json.dumps({"missing": ["us"]}))["credit"] == 0
    assert score.score_step(dictation, json.dumps({"text": "I like tea."}))["credit"] == 1
    assert 0.5 < score.score_step(dictation, json.dumps({"text": "I like te"}))["credit"] < 1
    answer = {
        "choices": ["sleep", "hunt", "bark"],
        "missing": "Most cats like warm places.",
        "highlight": ["at night", "sleep in boxes"],
        "idea": "Cats",
        "title": "About Dogs",
    }
    s = score.score_step(reading, json.dumps(answer))
    assert s["points"] == 8
    assert [x["credit"] for x in s["items"]] == [1, 1, 0, 1, 1, 0.8, 1, 0]
    assert score.score_step(reading, "not json")["credit"] == 0


def test_listen_and_complete_accepts_own_words():
    # Key words are "sick" and "flu". A synonym gets no credit, so the score is partial.
    assert score.idea_credit("I was ill with flu", "were sick with the flu") == 0.5
    assert score.idea_credit("Next monday", "next Monday") == 1
    assert score.idea_credit("recyling", "recycling") == 1  # a small spelling error


def test_every_shipped_answer_key_scores_full_marks():
    for folder in sorted((REPO / "rounds").iterdir()):
        for step in load_round(folder).steps:
            if step.skill in ("writing", "speaking"):
                continue
            k = step.key
            answer = {
                "read_select": {"real": k.get("real")},
                "fill_blanks": {"missing": k.get("missing")},
                "read_complete": {"missing": k.get("missing")},
                "listen_type": {"text": k.get("text")},
                "interactive_reading": {**k, "highlight": k.get("highlight")},
                "interactive_listening": {"complete": k.get("complete"), "turns": k.get("turns")},
            }[step.type]
            s = score.score_step(step, json.dumps(answer))
            assert s["credit"] == s["points"], step.id
