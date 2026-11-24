# Agent guide

det-coach is a local practice app for the writing and speaking tasks of the Duolingo
English Test. The user takes a timed round in the browser. A coding agent then grades
the answers and writes feedback that the app shows.

## What users ask for

| Request | Do this |
|---|---|
| "Grade my latest attempt", "give me feedback" | Follow [docs/grading.md](docs/grading.md) |
| "Make a new round", "more practice questions" | Follow [docs/authoring-rounds.md](docs/authoring-rounds.md) |
| "Start the practice", "open the app" | Run `uv run det-coach practice` in the background and give the URL |
| Questions about setup or commands | Answer from the [README](README.md) |

## Commands

The [README](README.md#commands) lists every command. Use `uv run det-coach <command>`.
For code changes, run `uv run pytest`, `uv run ruff check .` and `uv run ruff format .`.

## Layout

```
src/detcoach/
  tasks.py       task types and official times (the only place for times)
  rounds.py      load and validate rounds/<id>/round.json, expand tasks into steps
  attempts.py    attempts/<id>/: answers, recordings, manifest
  server.py      local HTTP server and JSON API (stdlib only)
  speech.py      spoken questions with macOS `say`
  transcribe.py  Whisper transcription (optional extras)
  metrics.py     speaking and writing measures
  feedback.py    grading packet and feedback.json validation
  static/        the app: index.html, app.css, app.js (no build step)
rounds/          practice content
rubric/          the scoring rubric for graders
attempts/        the user's answers (git ignores it)
```

## Rules

- Keep the runtime dependency free. Only the stdlib, plus optional Whisper extras.
- Keep the app free of a build step. Plain HTML, CSS and JavaScript.
- Prompts in `rounds/` are original. Never copy official or published test prompts.
- Photos have a free license and an attribution entry in `round.json`.
- Treat `attempts/` as the user's private data. Do not commit it or send it anywhere.
- Run the tests, `ruff check` and `ruff format` before you finish a code change.
