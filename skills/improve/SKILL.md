---
name: improve
description: Improves one element after a mixed verdict ("not bad, but...", "A has this, B has that") - gathers what we already know (her past verdicts, rules, references, research), writes a scoring grid, combines the best axes into 3 candidates, scores them on evidence from the engine, shows the best one side by side, and records her verdict for next time.
argument-hint: <element> [her words]
---

# /improve <element> [her words]

For when she says "pretty good, but it could be better", or "A has a better X, B a better Y".
Goal: the result that scores highest **with her**, built from everything we already know. The score only decides what
to show; **her verdict decides**, never the score.

## 0. What we know (before touching the code)
- **Her words of the day**, copied verbatim (the heaviest criterion).
- `.claude/skills/improve/verdicts.md`: her past tastes (what she liked, refused, and why). Pick the lines about this
  element or its family (character, animation, text, sound, place...). Format of a line is in step 7.
- The rules that apply: an **approved** line in the reference register (otherwise `/ref` first), the art-direction
  document (palette, budget), readability (silhouette and value, small + greyscale test), integrate-don't-copy.
- The research on how professionals solved it, if already done. No new research unless an axis is entirely unknown
  (then one sub-agent, medium effort).

## 1. Break it down
Each variant shown -> its **axes** (named parameters: rhythm, posture, amplitude, colour, size...).
For each axis: which variant she prefers (with her words) or "unknown". Write this table in the reply, short.

## 2. The scoring grid (written BEFORE making anything)
Out of 100, 4 to 6 criteria, each with its weight and the evidence expected:
- her words of the day: >= 50 points in total (e.g. "keep B's expression" 25, "keep C's posture" 25);
- her past tastes (verdicts.md) that apply;
- readability: reads by silhouette and value in the small + greyscale test, at play distance;
- eliminatory (score 0 if failed): nothing outside approved references, no generative model, budget held, tests green.

## 3. Three candidates
- **1 - the faithful mix**: each axis taken from the variant she preferred.
- **2 - the pushed mix**: the same, winning axes pushed one notch further.
- **3 - the side step**: the faithful mix + one "unknown" axis tried differently.
One step, one witness: each candidate differs from the others by named axes, not by chance.

## 4. Make and prove
By script (a Blender recipe through MCP, code in the game project), proof inside the engine: a preview capture,
or a short Movie Maker recording for anything that moves (`--write-movie <x.avi> --fixed-fps 30 --quit-after N`,
`--audio-driver Dummy`). Tests must stay green.

## 5. Score yourself
Really look at the images (a contact sheet of the key frames, small + greyscale test). For each candidate and each
criterion: a score and **one sentence of evidence** ("frame 4: the knee passes in front of the hip").
If no candidate reaches 85, or an eliminatory criterion fails: fix the faulty axis and redo, **3 rounds at most**.
Nothing that costs money or quota without her yes (no batch of agents).

## 6. Show
One single side-by-side sheet or video, opened on screen (one at a time), candidates titled by their letter and a short name.
In the reply: the best first, one line of score each, then the question (which one, or what still bothers her).

## 7. Learn
As soon as she answers, add one line at the top of `verdicts.md`:
`- YYYY-MM-DD · <element> · what she chose/refused · "her words" · my score was right: yes/no (and why)`.
If my score was wrong, fix the grid rule that failed (in that line): the next grid takes it into account.
The approved choice then follows the normal path (approved captures, docs, JOURNAL at `/end`).
