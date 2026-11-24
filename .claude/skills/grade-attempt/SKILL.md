---
name: grade-attempt
description: Grade a det-coach practice attempt and write feedback.json for the results page. Use when the user asks to grade, score, review or give feedback on a practice attempt or round.
---

# Grade an attempt

Do not grade in this conversation. This conversation can know the user and their
earlier rounds, and that knowledge biases a grade. Give the work to the `det-grader`
subagent, which follows [docs/grading.md](../../../docs/grading.md) and sees only
the answers.

1. Find the attempt id: `uv run det-coach attempts`, or `latest`.
2. Start the `det-grader` subagent with the prompt "Grade det-coach attempt <id>."
3. When it returns, run `uv run det-coach check-feedback <id>` yourself.
4. Tell the user the two estimates and the top priorities. The app shows the rest.
