# Grading an attempt

This document is the grading procedure for a coding agent. A person can follow it too.
The result is `attempts/<id>/feedback.json`. The results page in the app shows it.

## Procedure

1. Make the packet.

   ```bash
   uv run det-coach packet latest
   ```

   Use an attempt id in place of `latest` when the user names one. The command
   transcribes the recordings first, then prints the path of `packet.md`. If it
   says that no transcription backend is installed, tell the user the command it
   prints (for example `uv sync --extra mlx`). The first run downloads a Whisper
   model of about 1.5 GB.

2. Read `packet.md` completely. It contains every prompt, every answer, every
   transcript with its pauses, and the measures for each answer.

3. Open every photo file that the packet names. You cannot grade the content of a
   photo answer without the photo.

4. Read [`rubric/rubric.md`](../rubric/rubric.md).

5. Grade every answered step. Write `feedback.json` in the attempt folder, in the
   format below.

6. Validate it, and correct every problem that the command reports.

   ```bash
   uv run det-coach check-feedback latest
   ```

7. Tell the user that the feedback is ready in the app. Give the two estimates and
   the top priorities in two or three sentences.

## How to grade

- **Be strict.** The user practises for a real test. A high band that is not
  earned does not help. When you are not sure between two bands, use the lower one.
- **Quote the answer.** Each fix starts with the exact words that the user wrote
  or said (`original`). Then give a better version (`better`) and the rule or
  reason (`why`). Give 2 to 4 fixes for each answer, the most important first.
- **Use the measures.** For speaking, words per minute, pauses over 2 s, fillers
  and time used are evidence for fluency. A short answer limits content. In the
  packet, the transcript shows pauses of 1 s or more as `[1.8 s]`.
- **Pronunciation.** You only have a transcript. Words that Whisper heard with low
  confidence (`unclear words`) and words that do not fit the context can show
  pronunciation problems. Say in the note that this is an indirect judgement, and
  give a band only when there is evidence. Otherwise set the criterion to `null`.
- **Model answer.** For each answer, write a stronger answer at about the 150 band.
  Keep the user's own ideas and facts. Make it fit the task time: about 130 words
  per minute for speaking, and a length the user can type in the time for writing.
- **Estimates.** Give a Writing and a Speaking range. Weight each step by its task
  weight in the packet. A range is 10 or 15 points wide. Leave out a skill if
  the user answered none of its tasks.
- **Priorities.** Give 1 to 3 changes that would raise the score most, across all
  tasks. Each one is specific and the user can practise it.

## feedback.json

```json
{
  "version": 1,
  "attempt": "round-01-20261123-172652",
  "grader": "Claude Opus 5.5",
  "summary": "Two or three sentences on the attempt as a whole.",
  "estimate": { "writing": [120, 130], "speaking": [110, 120] },
  "priorities": [
    { "title": "Answer every part of the prompt", "detail": "In the Speaking Sample you described the failure but did not say what you do differently now." }
  ],
  "steps": {
    "photo-1": {
      "band": [115, 125],
      "criteria": {
        "content": { "band": [110, 120], "note": "Names the vendor and the jars, but not what the customer does." },
        "coherence": { "band": [120, 130], "note": "..." },
        "grammar": { "band": [115, 125], "note": "..." },
        "lexis": { "band": [120, 130], "note": "..." }
      },
      "strengths": ["Uses a present continuous for the actions."],
      "fixes": [
        { "original": "a man sell pickles", "better": "a man is selling pickles", "why": "Use the present continuous for an action in a photo." }
      ],
      "next_time": ["Add one inference, for example why the people are there."],
      "model_answer": "A vendor in a grey T-shirt is selling homemade pickles ..."
    }
  }
}
```

| Field | Required | Content |
|---|---|---|
| `version` | yes | `1` |
| `attempt` | yes | The attempt id |
| `grader` | yes | The model or person that graded |
| `summary` | yes | Two or three sentences |
| `estimate.writing`, `estimate.speaking` | no | `[low, high]` |
| `priorities` | yes | 1 to 3 objects with `title` and `detail` |
| `steps.<step id>` | for every answered step | One object per step id in the packet |
| `band` | yes | `[low, high]` for the step |
| `criteria` | yes | `content`, `coherence`, `grammar`, `lexis`, and for speaking `fluency` and `pronunciation`. Each is `{ "band", "note" }` or `null` |
| `strengths` | no | Short list |
| `fixes` | no | Objects with `original`, `better` and `why` |
| `next_time` | no | Short list |
| `model_answer` | no | A stronger answer |

Every band is `[low, high]` with multiples of 5 from 10 to 160, and `low <= high`.
`det-coach check-feedback` checks all of these rules.
