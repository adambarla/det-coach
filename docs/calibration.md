# Calibration

det-coach estimates scores with a coding agent, not with Duolingo's scoring models.
This page shows how close the estimates are to official scores, and how to check
again after a change to the rubric.

## Result

The test set is the 21 scored answers in section 6 of the
[Scoring Guide (2026)](https://englishtest-static.duolingo.com/media/resources/DET_Scoring%20Guide%20for%20Teachers%20%282026%29.pdf).
They cover all seven graded task types, three answers each, from 65 to 150. Each
answer comes with the Writing or Speaking subscore that the test taker received.

Two graders (Claude Opus 5.5, each in a fresh context, with no web access) estimated
a score for every answer, without the official scores or comments.

| Rubric | Answers | Mean error | Mean absolute error | Within 10 points |
|---|---|---|---|---|
| Bands only (before calibration) | all 21 | −23 | 23 | 9 of 42 |
| With the calibration anchors | all 21 | −3 | 5 | 39 of 42 |
| With the calibration anchors | 7 held out | −5 | 7 | 11 of 14 |

- Before calibration, the graders ranked the answers correctly (correlation 0.85 to
  0.91) and agreed with each other within 5 points on average. But they scored
  almost every answer 20 to 25 points too low. Official scores forgive errors
  that do not block meaning far more than a strict reading of the bands does.
- The rubric now has a *Calibration* section with paraphrased anchors for 14 of the
  answers. The other 7 (the second answer of each task) are held out. The held-out
  row is the honest measure of accuracy.
- After calibration the correlation is 0.97, and the two graders differ by 3 points
  on average.

## Limits

- Each official score is the subscore for the whole test, not for one answer. One
  answer can be better or worse than the test taker's level.
- 21 answers is a small set, and the held-out set has only 7. Treat the accuracy as
  about ±10 points.
- For speaking, the graders read a transcript. The official scorer hears the audio.
- Photo answers were graded without the photos.

## Run it again

Run the calibration after every change to `rubric/rubric.md` or `docs/grading.md`.

1. Download the Scoring Guide and extract the samples. This needs `pdftotext`
   (`brew install poppler`). The samples are copyrighted, so keep them in `.cache/`.

   ```bash
   python3 tools/calibration/extract.py "DET_Scoring Guide for Teachers (2026).pdf" .cache/calibration
   ```

2. Start two or more fresh subagents. Give each one only `rubric/rubric.md`, the
   *How to grade* section of `docs/grading.md` and `.cache/calibration/blind.md`.
   Forbid the web and every other file. Ask each one for a JSON list of
   `{"id", "estimate", "band"}`, saved as `.cache/calibration/<name>.json`.

3. Compare.

   ```bash
   python3 tools/calibration/compare.py .cache/calibration .cache/calibration/grader-1.json .cache/calibration/grader-2.json
   ```

Update the table above with the new numbers. If the held-out error grows, change
the rubric, not the anchors.
