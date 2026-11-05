---
name: start
description: Start of session - summarises the state (journal, alerts, fingerprints, git, open Blender windows) and proposes the next task. Run at the beginning of every session.
---

# /start

0. **Who are you?** The second line of the session-start script says it: `YOU ARE: GAME` or `YOU ARE: WORKSHOP`. Tell
   her first and stick to it. Read your section of `docs/sessions.md` and your memo (`docs/memo_<role>.md`, if any).
   - WORKSHOP: do not propose a production task (step 4); propose the "next time (WORKSHOP)" line of the JOURNAL.
     Do not touch the game, Godot or Blender, do not commit.
   - CODE: the second game session. She does not talk to you: no summary and no green light to wait for; tell `game`
     (SendMessage) which `[code]` task you take, and move on.
   - No role: ask her which one you are before any task.
1. Read the output of the session-start script (already in the context through the SessionStart hook). If missing, run it.
   - **The night**: if a night queue exists for today or yesterday and your role, read its "Summary" and tell her first
     (done, questions waiting for her on the dashboard, blocked).
   - CODE: take the first `[code]` task that GAME has not opened (not simply the first task).
   - **The rules review, every Monday** (her choice: a daily ritual made us go round in circles): at the first session of
     the Monday (the one that talks to her), run `python -I tools/verify_rules.py --review`.
     Show her the numbered list (rules of CLAUDE.md and memories) and every ⚠, then ask in one line:
     "Do you want to remove one? Give me its number, otherwise we keep everything." She removes what she wants; you add nothing.
     A rule only comes in on her yes, saying which one is merged or removed.
2. Summarise for her in 5-8 lines, in plain words:
   - what was done in the last session (JOURNAL);
   - **every ⚠** (journal, fingerprints) - first if there are any;
   - git state (clean or not);
   - open Blender windows.
3. **Fingerprints failing**: show the touched files and propose the restore from the protected tag
   (`git checkout protected-ok -- <protected folders>`), then run the session-start script again. Do nothing else until
   it is fixed or she says to go on.
4. Propose **the next task** (first `- [ ]` of `docs/production.md`): what, where, references needed.
   - **Task waiting**: look at the questions left unanswered on the dashboard. If there are some, say so first ("task X is
     waiting for your choice") and propose, in addition, a **second task** to move forward meanwhile, preferably code
     (never more than two open; back to the first as soon as she answers).
   - **Before proposing a "pending" choice** or a "next time" item: read the header of the code file concerned (grep
     `her choice|refused`). If the code carries a decision newer than the JOURNAL, **the code is the source of truth**:
     tell her, fix the JOURNAL and the task, and never propose again a direction already refused.
   - Visual/sound task: check that the element has an **approved** line in the reference register, otherwise propose `/ref` first.
5. If the task touches Blender: check the add-on status on the intended Blender window. If it does not answer, ask her to start it.
6. Wait for her green light before making anything.
