# Rubric

This rubric is a short paraphrase of the *DET Scoring Guide for Teachers (2026)*,
section 5. Read the official guide for the full text:

- [Scoring Guide (2026)](https://englishtest-static.duolingo.com/media/resources/DET_Scoring%20Guide%20for%20Teachers%20%282026%29.pdf)
- [Questions Guide (2026)](https://englishtest-static.duolingo.com/media/resources/Questions%20Guide%202026.pdf)

The test scores answers with its own models. This rubric helps a coding agent give a
similar judgement. It does not reproduce the official scores.

## Criteria

Writing tasks use four criteria. Speaking tasks use all six.

| Key in feedback.json | Criterion | What it asks |
|---|---|---|
| `content` | Content | Does the answer do every part of the task, stay on topic, use a suitable tone, and support ideas with details and examples? |
| `coherence` | Discourse coherence | Is the answer easy to follow? Do ideas come in a logical order, with linking words and pronouns that connect them? Writing also needs a clear structure. |
| `grammar` | Grammar | Range of structures (complex sentences, passive, conditionals, tenses) and accuracy. Writing also counts punctuation. |
| `lexis` | Lexis | Range and precision of words, natural collocations, correct word forms. Writing also counts spelling. |
| `fluency` | Fluency (speaking) | Speed, pauses at natural places, few restarts and fillers. Strong speakers often reach about 140 words per minute. |
| `pronunciation` | Pronunciation (speaking) | Intelligibility, clear sounds, correct word and sentence stress, intonation. |

## Score bands

Every band in feedback.json is a range of multiples of 5 between 10 and 160.
The official guide describes these ranges.

### 155 to 160

- **Content.** Does the full task. A photo answer names the key people, objects
  and actions and makes inferences. A summary gives who, the topic, the main
  points and the outcome, with no extra detail. Long answers are focused and
  well developed.
- **Coherence.** Very easy to follow. Ideas connect clearly.
- **Fluency.** Speaks at length. Pauses are short (usually under 2 seconds) and fall
  between ideas.
- **Grammar.** A very wide range. Only errors that expert speakers also make.
- **Lexis.** Broad and precise. Good collocations and idioms.
- **Pronunciation.** Clear and natural. The listener needs no effort.

### 130 to 150

- **Content.** Clear and suitable. Relevant ideas with examples. Some ideas are not
  explored in depth. A summary has small gaps.
- **Coherence.** Generally well organized. Some small problems with flow. Long
  writing has an introduction, body and conclusion.
- **Fluency.** Speaks at length without frequent hesitation. Pauses are mostly
  short and in suitable places.
- **Grammar.** A variety of structures (passive, conditionals, complex sentences),
  correct most of the time. Small errors do not block meaning.
- **Lexis.** A wide range, used naturally, with common collocations.
- **Pronunciation.** Most words are easy to understand. Some errors in sounds or
  stress.

### 100 to 125

- **Content.** Answers the question with most points. Some points are only partly
  developed. A summary can miss supporting ideas or the ending.
- **Coherence.** Mostly easy to follow. Uses linking words and pronouns.
- **Fluency.** Longer stretches on familiar topics, but not smooth. Some long or
  unnatural pauses, repetitions and self corrections. Somewhat slow.
- **Grammar.** Complex sentences with conjunctions, modals, relative clauses and
  conditionals, mostly correct.
- **Lexis.** Enough words for the main ideas. Some repetition and familiar phrases.
- **Pronunciation.** Most words are clear. Some errors reduce intelligibility.

### 60 to 95

- **Content.** Answers part of the question. Details and examples are basic or
  missing.
- **Coherence.** Somewhat organized. Basic linking words (and, but, because, so).
  Some connections are unclear.
- **Fluency.** Short stretches. Frequent, often long, silent pauses inside clauses.
- **Grammar.** Limited range (present and past simple, basic modals). Some errors
  block meaning.
- **Lexis.** Mostly correct but limited and general. Repetition.
- **Pronunciation.** Some control. Errors sometimes reduce clarity.

### 30 to 55

- **Content.** A basic attempt. A photo answer only names one or two things. Support
  is minimal.
- **Coherence.** Repetitive. Ideas are listed without connection.
- **Fluency.** Slow, with long pauses that break up ideas.
- **Grammar.** Basic forms with frequent errors.
- **Lexis.** A small set of common words, often imprecise.

### 10 to 25

Little relevant language, or no answer.

## Calibration

The official scores are higher than a strict reading of the bands above. In a blind
test, two graders that used only the bands scored 21 real answers about 23 points
below the scores that Duolingo gave them. The graders agreed with each other and
ranked the answers correctly, so the error was a constant offset, not noise.
[docs/calibration.md](../docs/calibration.md) describes the test.

Use these rules to remove the offset:

- **Errors that do not block meaning cost little.** Missing articles, wrong
  prepositions, small spelling errors and comma splices are normal at 130 to 140.
- **A short, simple answer that is correct and on task scores well.** Range and
  development raise the score above 140. Their absence does not pull a clear
  answer below 125.
- **Below 100 means that communication breaks down**: fragments, unclear sentences,
  most of the task missing, or language too limited for the ideas.
- **Score what the answer shows**, then compare it with the anchors below. Do not
  lower a band only because you are not sure.

### Anchors

These describe real answers from the *Scoring Guide (2026)*, section 6, with the
subscore that the test taker received. They are paraphrased. Read section 6 of the
guide for the full answers.

| Task | Score | What the answer did |
|---|---|---|
| Write About the Photo | 140 | Four short, correct sentences that name the scene, the background and one detail. No inference. Two unnatural word choices. |
| Write About the Photo | 85 | One and a half sentences, cut off. Missing articles, a spelling error and an agreement error. Names two objects only. |
| Interactive Writing | 150 | Both parts answered in full: clear steps with sequence words, then a cause and effect. A few errors in tense and verb form. |
| Interactive Writing | 90 | Both parts cut off. Frequent spelling, capitalization and verb form errors, but the story and the point are clear. |
| Writing Sample | 150 | A clear position developed with several concrete points about one country, with good vocabulary. One agreement error and an unfinished last sentence. |
| Writing Sample | 85 | Lowercase start, many spelling errors, unclear sentences and a personal example that is cut off. |
| Speak About the Photo | 145 | About 130 words. Setting, people, clothes and actions, with two inferences. Natural phrases and only small errors. |
| Speak About the Photo | 85 | Broken sentences with missing verbs and wrong forms. The listener must guess the meaning of several sentences. |
| Read, Then Speak | 140 | Answers all three questions with a clear main idea, but loosely organized, with fillers and a few unclear phrases. |
| Read, Then Speak | 65 | Repeats the question, then gives short broken clauses on a technical topic. Many restarts and form errors. Cut off. |
| Interactive Speaking | 135 | Six direct answers, each with a reason or a real example. Many fillers ("like", "em"), restarts and some small errors. |
| Interactive Speaking | 90 | Answers are on topic but very short or unclear, with frequent errors in basic verb forms and word order. |
| Speaking Sample | 145 | Uses the full time. Benefits and disadvantages, each with a personal example. Many fillers ("um", "you know") and some repetition. |
| Speaking Sample | 80 | Long, but circles one idea with constant restarts, wrong pronouns and verb forms. The main point is clear only in parts. |

Fillers and restarts cost much less than a strict reading suggests: both 135 to 145
speaking anchors use them often. Range of language and full, relevant answers
weigh more.

## Task notes

These notes come from the task descriptions in the official guides.

- **Write About the Photo** (60 s). Describe what is visible and what is happening.
  Inferences help at the top bands.
- **Interactive Writing** (5 min, then 3 min). The follow-up question needs a direct
  answer with new detail, not a repeat of part 1.
- **Summarize the Conversation** (75 s). Who spoke, the topic, the key points and
  the outcome. Leave out small details.
- **Writing Sample** (5 min). A clear position, developed with reasons and
  examples, in paragraphs. Schools can read this answer.
- **Speak About the Photo**, **Read, Then Speak** (up to 90 s). Use most of the time.
  Cover every bullet of the prompt.
- **Listen, Then Speak** (up to 90 s, from the 2025 samples). The same as Read, Then
  Speak, but the question was heard, not read. Answer every part of it.
- **Interactive Speaking** (35 s each). Answer the question directly, then give a
  reason or an example.
- **Speaking Sample** (up to 3 min). An organized answer to every part of the
  prompt. Schools can watch this answer.
