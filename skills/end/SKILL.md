---
name: end
description: End of session - checks (non-blocking), a JOURNAL entry, the production task ticked, a commit through the project's commit script and a backup bundle.
argument-hint: [-close]
---

# /end

Nothing here blocks the commit: a failed check becomes a ⚠ line in the JOURNAL.

1. **Checks**
   - `python tools/verify_refs.py` (every asset has an approved reference line)
   - `python tools/fingerprints.py --verify` (sha256 of the protected folders)
   - `python -I tools/verify_rules.py` (against dust: size caps of CLAUDE.md, of the memories and of the production
     tasks, duplicates, expired rules). A task you just wrote that is over the cap: shorten it (history goes to
     `docs/production_history.md`); anything else becomes a ⚠.
   Note every failure.
   - **Tests never weakened**: compare the number of checks with the last commit:
     `git show HEAD:game/tests/run_tests.gd | grep -c 'check('` against `grep -c 'check(' game/tests/run_tests.gd`.
     Fewer than before -> ⚠ with the list of vanished tests (`git diff HEAD -- game/tests`) and the reason; a loosened
     threshold inside a modified `check(` counts too. Only her yes allows removing a test.
   - `python tools/decisions_of_the_day.py`: the list of today's decisions (dashboard verdicts + "her choice / refused /
     approved" written in code and docs). **Every** choice and refusal in this list, and every choice given in the
     conversation, goes into `decided:` in the JOURNAL **and** into the production task. A "pending" choice that has been
     settled is rewritten. Never copy the old "next time" without checking each point. Run the script again after
     writing: no more `??` (or a `??` that is explained).
2. **JOURNAL.md**: new entry **at the top** (under the title), format:
   ```
   ## YYYY-MM-DD - <short title>
   - done: ...
   - decided: ...
   - next time: ...
   - ⚠ <each failed check, with the file>
   ```
   A ⚠ always starts its line (`- ⚠ ...`): that is how the session-start script finds it again.
   If a ⚠ from an older entry was fixed during the session, replace its `- ⚠` with `- ✓ fixed (YYYY-MM-DD) -`,
   otherwise it comes back at every `/start`.
3. **Task**: if the work is finished and its proof approved, tick it `- [x]` in `docs/production.md`.
4. **Commit** (never a `git add` that names a protected folder):
   `powershell -NoProfile -File tools\commit.ps1 "<message>"`
   Add `-close` only if a task closes (includes the `.blend` source files).
5. Report: the commit hash, that the bundle is written, and any ⚠. If the script reports uncommitted changes in a
   protected folder, say it clearly and propose the restore from the protected tag.
6. End with one line on its own: **"Everything is saved - you can type `/clear`."** (Claude cannot run `/clear`
   itself; after `/clear`, the SessionStart hook prints the state, then `/start`.)
