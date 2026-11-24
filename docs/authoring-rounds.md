# Writing a round

A round is a folder in `rounds/` with a `round.json` file and a `photos/` folder.
The app adds the official times. A round never sets times.

## Rules

- **Write original prompts.** Do not copy prompts from official materials, practice
  sites or books. They are copyrighted. Use the same format and difficulty.
- **Use free photos only.** `det-coach fetch-photo` downloads a photo from Wikimedia
  Commons and accepts only CC0, public domain, CC BY and CC BY-SA. It prints the
  attribution entry for `round.json`.
- **Choose clear photos.** A good photo shows people who do something, in a place
  that has detail to describe. Avoid text in the photo, famous people and brands.
- **Use everyday topics.** Study, work, travel, technology, health, environment,
  free time. A prompt asks for an experience or an opinion that every adult can
  give.

## Steps

1. Make the folder and copy a round as a start.

   ```bash
   mkdir -p rounds/round-04/photos
   cp rounds/round-01/round.json rounds/round-04/
   ```

2. Change `id` to the folder name and give a `title`.

3. Find photos on [Wikimedia Commons](https://commons.wikimedia.org) and download them.

   ```bash
   uv run det-coach fetch-photo round-04 "File:Example photo.jpg" --name cafe.jpg
   ```

   Add the printed entry to `photos` in `round.json`.

4. Write the tasks (see the format below).

5. Validate the round.

   ```bash
   uv run det-coach check
   ```

6. Look at each screen in the app at `http://127.0.0.1:8765/#/preview/round-04/<step id>`.
   A step id is the task id. Tasks with more than one screen add `-1`, `-2` and so
   on (Interactive Writing parts, Interactive Speaking questions and each item of a
   reading or listening set). The summary of an Interactive Listening task is
   `<id>-summary`.

## Format

A round can have any of the task types. A full test has these tasks, in the order of
the official [Question Guide](https://englishtest-static.duolingo.com/media/resources/Questions%20Guide%202026.pdf).
The count column gives the official number for one test. `rounds/round-03` is a full
test.

| Type | Count in a test | Fields | Content |
|---|---|---|---|
| `read_select` | 15 to 18 words | `words` | Real words and invented words that look real |
| `fill_blanks` | 6 to 9 sentences | `sentences` | One sentence for each item, with one `{word}` |
| `read_complete` | 3 to 6 paragraphs | `title`, `passage` | A paragraph with `{words}` to finish |
| `listen_type` | 6 to 9 sentences | `sentences` | Sentences for the user to type |
| `interactive_reading` | 2 to 3 passages | see below | One story and one text with facts |
| `interactive_listening` | 2 to 3 conversations | see below | One with a professor, one with a student |
| `write_photo` | 3 | `photo` | A photo to describe |
| `interactive_writing` | 1 | `prompt`, `follow_up` | A question, then a follow-up question on the same topic |
| `speak_photo` | 1 | `photo` | A photo to describe |
| `read_then_speak` | 1 | `prompt`, `bullets` | A topic with 3 guide questions |
| `interactive_speaking` | 6 to 8 questions | `topics` | 2 topics with 3 or 4 questions each |
| `writing_sample` | 1 | `prompt` | An opinion question |
| `speaking_sample` | 1 | `prompt` | A question about an experience or opinion |

`summarize_conversation` (field `conversation`, 8 to 12 lines) is the summary task
without the listening questions. Interactive Listening makes its own summary, so a
full test does not need it.

Conversation speakers are `professor`, `student`, `student2` or `interviewer`.
Each one gets a different voice. Interactive Speaking questions are spoken by the
`interviewer`. The first question of a topic introduces the topic, as in the
real test.

### Words to finish

In `fill_blanks` and `read_complete`, put a word in braces. The app shows the first
half of the word and the user types the rest. To choose the split yourself, write
`{sh|own}`: the app shows "sh" and the answer is "own".

The official rules for `read_complete`, which `det-coach check` enforces:

- The first and last sentences have no blanks.
- Two blanks are never next to each other.
- Use at least 5 blanks. Do not use names or acronyms as blanks.

```json
{ "id": "complete-1", "type": "read_complete", "title": "Why We Yawn",
  "passage": "Almost every animal yawns. For a long {time}, scientists {believed} that ... It is hard to read about yawning without doing it yourself." }
```

### Interactive Reading

`passage` is the first part of the text. Each `{right|wrong|wrong}` is a word to
choose from a list (3 to 10 of them). The right word comes first, and the app mixes
the order. `missing_sentence` goes after `passage`, and `rest` comes after it.
The answers of `highlight` are words copied from the full text.

```json
{
  "id": "reading-1", "type": "interactive_reading",
  "passage": "Dark roads {absorb|reflect|forget} sunlight ...",
  "missing_sentence": { "answer": "This extra heat can be dangerous ...", "wrong": ["...", "..."] },
  "rest": "Some cities are now fighting back. ...",
  "highlight": [
    { "question": "Why do dark roads make cities hotter?", "answer": "absorb sunlight during the day" },
    { "question": "How much can these changes lower temperatures?", "answer": "by one or two degrees" }
  ],
  "main_idea": { "answer": "...", "wrong": ["...", "...", "..."] },
  "best_title": { "answer": "...", "wrong": ["...", "...", "..."] }
}
```

### Interactive Listening

The narrator reads `scenario`. The user completes 3 or 4 `complete` sentences about
the scenario, then talks with the `partner`. A `you` turn is a choice of replies
(5 or 6 of them in a conversation). Wrong replies do not fit the scenario, do not
match what the partner said, use the wrong words or pronouns, or are too formal or
too informal. The app adds the summary task after the conversation.

```json
{
  "id": "listening-1", "type": "interactive_listening", "partner": "professor",
  "scenario": "You are a student in a biology course. You missed last week's lab ...",
  "complete": [ { "sentence": "Your lab report is due ___.", "answer": "next Monday" } ],
  "conversation": [
    { "you": { "answer": "Hi, Professor Lee. Do you have a few minutes?", "wrong": ["Hey, what's up?", "..."] } },
    { "partner": "Of course. Come in." }
  ]
}
```

### Round file

```json
{
  "id": "round-04",
  "title": "Cities, sleep and teamwork",
  "tasks": [
    { "id": "photo-1", "type": "write_photo", "photo": "cafe.jpg" }
  ],
  "photos": {
    "cafe.jpg": { "title": "...", "author": "...", "license": "CC BY 4.0", "source": "https://commons.wikimedia.org/wiki/File:..." }
  }
}
```

`det-coach check` reports every problem in a round, with the task that has it.
