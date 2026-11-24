# det-coach

Practice every task of the Duolingo English Test with the official timings, then get
feedback on your writing and speaking from a coding agent such as Claude Code.

The official practice test gives you a score, but it does not tell you what to fix.
det-coach records your answers on your own computer. Your agent then grades each answer
against the official scoring criteria. It shows you score bands, your top priorities,
corrections of your own sentences and a stronger model answer.

![The Write About the Photo task](docs/images/exam-photo.png)

## Features

- **All the task types of the 2026 test** with the official times. Reading: Read and
  Select, Fill in the Blanks, Read and Complete and Interactive Reading. Listening:
  Listen and Type and Interactive Listening. Writing and speaking: the photo tasks,
  Interactive Writing, Summarize the Conversation, Read, Then Speak, Interactive
  Speaking and the two samples.
- **Instant scores for reading and listening.** det-coach marks each answer and shows
  the right one, with partial credit where the real test gives it.
- **A test-like experience.** The screens follow the official ones: one timed screen
  at a time, no pause button, spell check off, spoken questions that play once, and a
  Continue button that stays gray until you answer.
- **Practice one task at a time.** The home page lists every task type with your recent
  result and marks the one to work on next. Practice starts a short set of new
  questions of that type. Drills never use the questions of a full test that you have
  not taken, so each full test stays new.
- **Full tests and sections.** Take a whole round, or only its reading, listening,
  writing or speaking tasks. The writing section needs no microphone.
- **Local and private.** The app, the recordings and the transcription run on your
  computer.
- **Feedback in the app.** Score bands for each criterion, fixes that quote your own
  words, model answers, and your recordings with pauses marked in the transcript.
  To remove an attempt, click Delete at the bottom of its page.
- **Open content.** Rounds are JSON files with original prompts and freely licensed
  photos. `round-03` and `round-04` are full tests. No two rounds share a prompt, a word or
  a photo. Your agent can write new rounds for you.

## Requirements

- Python 3.10 or newer and [uv](https://docs.astral.sh/uv/)
- Chrome, Safari or Firefox, with a microphone
- macOS for the best voices. On other systems the browser's own voice reads the
  questions.
- [ffmpeg](https://ffmpeg.org) on macOS, to join the voices of a conversation and to
  transcribe recordings with mlx-whisper

## Quick start

```bash
git clone https://github.com/adambarla/det-coach.git
cd det-coach
uv run det-coach practice
```

Your browser opens at http://127.0.0.1:8765. Choose a task to practice, or a full test.
Your answers save to `attempts/` as you go. Practice sets save to `drills/`.

## Commands

| Command | What it does |
|---|---|
| `uv run det-coach practice` | Start the app and open it in the browser. Add `--round round-02` to go straight to a round, `--section writing` (with `--round`) to take one section, `--port` to change the port, `--no-open` to not open a browser. |
| `uv run det-coach attempts` | List your attempts and whether they have feedback. |
| `uv run det-coach transcribe [attempt]` | Transcribe the recordings of an attempt. `--force` transcribes again. |
| `uv run det-coach packet [attempt]` | Transcribe, then write `packet.md`: every prompt, answer, transcript and measure in one file for grading. |
| `uv run det-coach check-feedback [attempt]` | Validate the `feedback.json` of an attempt. |
| `uv run det-coach check` | Validate every round in `rounds/`. |
| `uv run det-coach fetch-photo <round> "File:<title>"` | Download a freely licensed photo from Wikimedia Commons into a round and print its attribution. |

`[attempt]` is an attempt id. Without it, the commands use the latest finished attempt.
Add `--help` to any command for all its options.

## Get feedback

Grading needs a coding agent and a local Whisper model for the recordings.

1. Install transcription once. The first run downloads a model of about 1.5 GB.

   ```bash
   uv sync --extra mlx       # Apple Silicon
   uv sync --extra whisper   # other systems
   ```

2. Open your coding agent in the `det-coach` folder and ask:

   > Grade my latest det-coach attempt.

   In Claude Code you can also type `/grade-attempt`. Other agents read
   [AGENTS.md](AGENTS.md).

3. The results page in the app shows the feedback as soon as the agent saves it.

The agent follows [docs/grading.md](docs/grading.md) and the
[rubric](rubric/rubric.md), which paraphrases the official
[Scoring Guide](https://englishtest-static.duolingo.com/media/resources/DET_Scoring%20Guide%20for%20Teachers%20%282026%29.pdf).
You can also grade by hand: run `det-coach packet` and read `packet.md`.

![The results page](docs/images/results.png)

### What the feedback can and cannot do

- The reading and listening points are a share of right answers, not a DET score.
  The real test adapts these questions to you, so the same share can mean different
  scores.
- The writing and speaking bands are estimates. The real test uses its own scoring
  models. On 21
  officially scored answers, the estimates are within about 10 points of the official
  score. [docs/calibration.md](docs/calibration.md) shows the test.
- Grading runs in a separate subagent that sees only your answers, so the grade does
  not depend on what your agent knows about you.
- Pronunciation is the weakest criterion. The agent reads a transcript and cannot
  hear you. It only uses indirect evidence, such as words that the transcription
  model heard with low confidence.
- Fluency uses measured evidence: words per minute, pauses and fillers.
- If your agent runs on a cloud model, the packet (your written answers and the
  transcripts) goes to that provider. Your recordings stay on your computer.

## Natural voices on macOS

The spoken questions use the macOS `say` command. Premium voices sound much more
natural. Download some in **System Settings › Accessibility › Spoken Content ›
System Voice › Manage Voices**, for example *Ava (Premium)*, *Zoe (Premium)*,
*Jamie (Premium)* and *Serena (Premium)*. Then restart `det-coach practice`.
The app selects the best voices that are installed.

## More rounds

Each folder in [`rounds/`](rounds) is a round. To make a new round, ask your agent:

> Make a new det-coach round about travel and health.

Or write one yourself with [docs/authoring-rounds.md](docs/authoring-rounds.md).

## Official sample questions

Duolingo publishes a booklet of official sample questions with audio
([PDF](https://englishtest-static.duolingo.com/media/resources/GPN%20DET%20Sample%20Questions%20-%20Full.pdf)).
Two scripts turn it into local rounds: 4 full tests (`official-test-01` to
`official-test-04`) with as many questions of each type as the real test, and a pool
of all the other questions for practice by task.

```bash
curl -o .cache/booklet.pdf "https://englishtest-static.duolingo.com/media/resources/GPN%20DET%20Sample%20Questions%20-%20Full.pdf"
uv run --with pymupdf --with zxing-cpp --with pillow python tools/booklet/extract.py .cache/booklet.pdf .cache/booklet
python3 tools/booklet/make_rounds.py .cache/booklet
```

The extractor reads the QR codes in the booklet and downloads the recordings for
Listen and Type. The booklet has no recordings for Interactive Listening, so the app
speaks those conversations. The rounds leave out Listen, Then Speak, which the current
test no longer uses. The booklet content belongs to Duolingo, so `.gitignore` keeps
these rounds out of the repository. Do not share them.

When these rounds exist, the home page, the drills and the progress use only them.

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format .
```

The app is plain HTML, CSS and JavaScript in `src/detcoach/static/`, with no build step.
The server uses only the Python standard library.
[AGENTS.md](AGENTS.md) describes the layout of the code.

## Credits and license

The code is under the [MIT License](LICENSE). The photos come from Wikimedia Commons
under their own free licenses. Each `round.json` lists the author, license and source
of its photos, and the results page shows them.

det-coach is an independent project. It is not affiliated with or endorsed by
Duolingo. "Duolingo English Test" is a trademark of Duolingo, Inc.
