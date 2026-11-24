---
name: grade-attempt
description: Grade a det-coach practice attempt and write feedback.json for the results page. Use when the user asks to grade, score, review or give feedback on a practice attempt or round.
---

# Grade an attempt

Follow [docs/grading.md](../../../docs/grading.md) step by step. In short:

1. Run `uv run det-coach packet <attempt id or latest>` and read the `packet.md` it prints.
2. Open every photo that the packet names, and read `rubric/rubric.md`.
3. Write `attempts/<id>/feedback.json` in the format of docs/grading.md.
4. Run `uv run det-coach check-feedback <attempt>` until it reports no problems.
5. Tell the user the two estimates and the top priorities. The app shows the rest.

Be strict and quote the user's exact words in every fix.
