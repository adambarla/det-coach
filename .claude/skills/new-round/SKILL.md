---
name: new-round
description: Write a new det-coach practice round with original prompts and freely licensed photos. Use when the user asks for a new round, more practice questions or a round on a topic.
---

# Write a new round

Follow [docs/authoring-rounds.md](../../../docs/authoring-rounds.md).

- Use the next free id (`round-03`, `round-04`, ...).
- Write original prompts. Never copy official or published test prompts.
- Get photos with `uv run det-coach fetch-photo`, and add each printed entry to `photos`.
  Open each photo before you use it, to check that it has enough to describe.
- Run `uv run det-coach check` until it reports `ok` for the round.
- Give the user the link `http://127.0.0.1:8765/#/exam/<round id>`.
