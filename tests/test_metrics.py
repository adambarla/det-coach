from detcoach import metrics


def words(*spec):
    return [{"word": w, "start": s, "end": e, "probability": p} for w, s, e, p in spec]


def test_speaking_counts_pauses_fillers_and_rate():
    m = metrics.speaking(
        words(
            ("I", 1.0, 1.2, 0.9),
            ("um", 1.3, 1.5, 0.9),
            ("like", 1.6, 1.9, 0.9),
            ("trains", 4.2, 4.6, 0.3),
            ("a", 4.7, 4.8, 0.9),
            ("lot.", 4.9, 5.2, 0.9),
        ),
        slot_seconds=35,
    )
    assert m["words"] == 5  # the filler does not count
    assert m["fillers"] == 1
    assert m["pauses_over_2s"] == 1
    assert m["longest_pause_seconds"] == 2.3
    assert m["start_delay_seconds"] == 1.0
    assert m["unclear_words"] == ["trains"]
    assert m["words_per_minute"] == round(5 / 4.2 * 60)


def test_speaking_handles_silence():
    assert metrics.speaking([], 90)["silent"] is True


def test_writing_measures():
    m = metrics.writing("I like trains. Trains are fast!\n\nI like them a lot.")
    assert (m["words"], m["sentences"], m["paragraphs"]) == (11, 3, 2)
