# Designing the data

## Example format (one JSON object per line)

```json
{"id": "reaction-0-12-1", "kind": "reaction", "split": "train", "situation": "FSD jump",
 "state": {"game_state": "<exactly what the app sends>", "event": "FSD jump"},
 "questions": {"speak": {"type": "noul", "instructions": "...", "criteria": {"true": "...", "false": "..."}}},
 "gold": {"speak": true}}
```
`kind` groups metrics (one bar chart per kind on the dashboard). `situation` is a free label for filtering.
`gold` is a bool for noul, the option name for choice. Keep extra fields (e.g. `prompt`) if they help analysis.

## Where labels may come from

| Source | Trust | Example |
|---|---|---|
| A fact the model can read in its input | high | "Is the ship overheating?" from the overheating flag that also wrote the sentence |
| The user's instruction applied to those facts | high | prompt "only if fuel is low" + low-fuel flag → yes |
| The user's own labelled examples | high | recorder intent "LandingGearToggle" |
| A teacher model (hosted reference, big LLM) | medium | only for cases the rules cannot decide; review a sample |
| Your own idea of the right tactic | none | do not do this; ask the user or make it an instruction |

## Splits that measure something

- Hold out whole templates: 2 phrasings per action, every 4th prompt, every 5th talk line. A random row split
  leaks the same sentence into train and test.
- Benchmark sentences used earlier must never appear in training.
- Real user data: split by collection session. Data you inspected (to design augmentations) goes to train.
- After you study test errors, that test is spent. Collect a new small set for the next honest number.

## Balance and coverage

- Per question, "yes" between ~10% and ~90%. Rare conditions need boosted sampling (e.g. combat during an
  overheating event) or the model learns "always no".
- Every instruction/prompt needs enough rows (dozens). Event-specific prompts are rarer than general ones:
  sample them first.
- Vary everything the model should ignore: names, numbers, sentence order (if the app's order changes between
  runs, e.g. a frozenset, generate under several hash seeds).

## Negatives that matter

The first real-speech test showed every false key press came from sentences that mention an action without
asking for it. Generate them on purpose for every action:
- negation: "don't X yet", "I don't need X right now"
- questions: "why is X on", "how many X do I have", "does X use energy"
- past tense / story: "I used X and it saved me"
- reminders and later: "remind me to X later", "X when we get there"
- feedback: "good thing you didn't X"

## Speech-to-text realism

Synthetic sentences are clean; real ones are not. From the first recording session, collect the confusions
the STT makes (e.g. hardpoints → "heart points", pips → "peeps", chaff → "chuff") and inject them with some
probability, plus the STT's formatting (Whisper: capital letter, final full stop). Only use confusions from
sessions that are not the test.

## Review page intro (template)

```html
<div><p class="eyebrow">What changed</p><h2>...</h2></div>
<p>...</p>
<div><p class="eyebrow">Decisions for you</p></div>
<ul><li><b>D1 · topic.</b> The question. <i>Now: the default the data uses.</i></li></ul>
<div><p class="eyebrow">Findings</p></div>
<ul><li>Something the app's input never states, so the model cannot learn it.</li></ul>
```
