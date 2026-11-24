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
   mkdir -p rounds/round-03/photos
   cp rounds/round-01/round.json rounds/round-03/
   ```

2. Change `id` to the folder name and give a `title`.

3. Find photos on [Wikimedia Commons](https://commons.wikimedia.org) and download them.

   ```bash
   uv run det-coach fetch-photo round-03 "File:Example photo.jpg" --name cafe.jpg
   ```

   Add the printed entry to `photos` in `round.json`.

4. Write the tasks (see the format below).

5. Validate the round.

   ```bash
   uv run det-coach check
   ```

6. Look at each screen in the app at `http://127.0.0.1:8765/#/preview/round-03/<step id>`.
   Step ids are the task ids, with `-1`, `-2` added for Interactive Writing parts
   and Interactive Speaking questions.

## Format

A full round has these tasks, in this order:

| Type | Fields | Content |
|---|---|---|
| `write_photo` (3 times) | `photo` | A photo to describe |
| `interactive_writing` | `prompt`, `follow_up` | A question, then a follow-up question on the same topic |
| `summarize_conversation` | `conversation` | 8 to 12 lines between two speakers |
| `writing_sample` | `prompt` | An opinion question |
| `speak_photo` | `photo` | A photo to describe |
| `read_then_speak` | `prompt`, `bullets` | A topic with 3 guide questions |
| `interactive_speaking` | `topics` | 2 topics with 3 questions each |
| `speaking_sample` | `prompt` | A question about an experience or opinion |

Conversation speakers are `professor`, `student`, `student2` or `interviewer`.
Each one gets a different voice. Interactive Speaking questions are spoken by the
`interviewer`. The first question of a topic introduces the topic, as in the
real test.

```json
{
  "id": "round-03",
  "title": "Cities, sleep and teamwork",
  "tasks": [
    { "id": "photo-1", "type": "write_photo", "photo": "cafe.jpg" },
    {
      "id": "conversation",
      "type": "summarize_conversation",
      "conversation": [
        { "speaker": "student", "text": "Hi, do you have a minute?" },
        { "speaker": "professor", "text": "Sure, come in." }
      ]
    }
  ],
  "photos": {
    "cafe.jpg": { "title": "...", "author": "...", "license": "CC BY 4.0", "source": "https://commons.wikimedia.org/wiki/File:..." }
  }
}
```

`det-coach check` reports every problem in a round, with the task that has it.
