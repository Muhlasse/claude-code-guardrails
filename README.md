# claude-code-guardrails

**One person, several Claude Code sessions, one game. The rules are code, not wishes.**

I make a first-person horror game demo in Godot, alone. Several Claude Code sessions work on it at the same time, each with a role (`game`, `code`, `workshop`, `sound`, `video`). Some keep working at night.

Every rule that matters is a **Claude Code hook**: plain Python, covered by tests (176 checks, 0 failures).

## The six hooks at a glance

| Hook | Prevents | How |
|---|---|---|
| [`guard.py`](hooks/guard.py) | Writing into protected folders, `blender -b` | Reads every shell / Blender command before it runs; fails closed |
| [`timer.py`](hooks/timer.py) | Working past the agreed time | When time is up, work tools are denied; only the human extends |
| [`relay.py`](hooks/relay.py) | A conversation too long to stay sharp | Above 150k tokens: write a handoff note, restart fresh |
| [`night.py`](hooks/night.py) | A night session that stops too early, or never | Keeps it working until she wakes up, paced on the quota |
| [`continuous.py`](hooks/continuous.py) | A background session that stalls silently | Each reply ends with a `STATUS:` line the dashboard reads |
| [`language.py`](hooks/language.py) | Replies in English when she works in French | Counts the words; asks again in French once |

Each hook has its own test file in [`hooks/tests/`](hooks/tests/).

## How it fits together

```
   human
     |  talks to the game session, answers on a local dashboard
     v
   Claude Code sessions: game | code | workshop | sound | video
     |  every tool call and every end of reply goes through the hooks
     v
   PreToolUse        guard.py, timer.py
   PostToolUse       timer.py, relay.py
   Stop              night.py, continuous.py, language.py
   UserPromptSubmit  night.py --wake
     |  state files (JSON)
     v
   local dashboard (not in this repo)
```

The guard fails closed: any error means "no". The other hooks fail open: any error means they step aside, so a bug never jams a session.

## Each hook in detail

<details>
<summary><b>guard.py</b> — protected folders, Blender only through MCP</summary>

- Near a protected path, only read-only commands pass (`cat`, `ls`, `grep`, `git status/log/diff/show`...).
- Refused: redirections (`>`), `$( )`, backticks, `Invoke-Expression`, a wildcard that could reach a protected folder (`rm docs/st*`).
- Also refused: `blender -b`, scripts reserved to the human, Blender Python with `subprocess` / `os.system`.
- Every refusal goes to a JSONL log.
- Known limit, written in the file: it reads text, so a script written to disk and then run escapes it. Last line of defence: a sha256 fingerprint check and a restore from a git tag.

Test: [`test_guard.py`](hooks/tests/test_guard.py), 68 checks, including the false positives it once had.
</details>

<details>
<summary><b>timer.py</b> — timeboxing</summary>

- A session starts its timer: `--start game 90 "the door"`.
- 15 minutes before the end, it is told once.
- Time up: `Edit`/`Write` (outside wrap-up files), Blender, launching Godot and new sub-agents are denied. Reading, asking and committing still pass.
- A session cannot restart its own timer. At night, elapsed time does not block, but her "stop" does.

Test: [`test_timer.py`](hooks/tests/test_timer.py), 28 checks.
</details>

<details>
<summary><b>relay.py</b> — context-window handoff</summary>

- Claude Code cannot type `/clear` by itself. Above 150k tokens, the session is told once: finish, write a handoff note, run `relay.py --ready <role>`.
- `--ready` refuses a missing note, one older than 30 minutes, or shorter than 200 bytes.
- The dashboard then reopens a fresh session on that note. Never at night.

Test: [`test_relay.py`](hooks/tests/test_relay.py), 15 checks.
</details>

<details>
<summary><b>night.py</b> — unattended night runs</summary>

- After the human's "ok", the Stop hook sends the session back to its queue until she wakes up.
- Sub-agent reports, other sessions and task notifications do not count as her waking up.
- Quota pacing: weekly usage stays under a straight line from 0 % to 100 % over the week; above it, the session pauses and resumes later.
- "Nothing left to do" is refused until the summary names every open task.
- Hard stops: 16 hours, 200 relaunches. An "away" mode does the same in the daytime.

Test: [`test_night.py`](hooks/tests/test_night.py), 36 checks.
</details>

<details>
<summary><b>continuous.py</b> — background sessions</summary>

- Every reply ends with `STATUS: continue | waiting for her choice | waiting for <session> | nothing - <detail>`.
- On `continue`, the session goes back to work; the state is written for the dashboard.
- Never above the quota line; 40 `continue` in a row means a pause.

Test: [`test_continuous.py`](hooks/tests/test_continuous.py), 19 checks.
</details>

<details>
<summary><b>language.py</b> — replies in her language</summary>

- A written rule was not enough. The Stop hook counts common English and French words since her last message (code and links ignored).
- If English wins, it blocks once and asks for the reply again in French.

Test: [`test_language.py`](hooks/tests/test_language.py), 10 checks.
</details>

**Permissions.** [`examples/settings.json`](examples/settings.json) wires the hooks and adds what Claude Code can do by itself: bypass mode off, protected folders denied to `Edit`/`Write`, no generative 3D tool, asset imports always asked.

## Also in this repo

- [`skills/start`](skills/start/SKILL.md), [`skills/end`](skills/end/SKILL.md): the session ritual (state summary, journal, one commit script).
- [`skills/improve`](skills/improve/SKILL.md): after a mixed verdict, a scoring grid first, then 3 candidates; the human decides.
- [`agents/reviewer.md`](agents/reviewer.md): predicts whether an attempt will be refused, from the human's past verdicts.
- [`rules/CLAUDE.md`](rules/CLAUDE.md): the project rules (one rule in, one out; pre-mortem; fixed time; human in the loop).

## In industry terms

| What we call it | Industry term |
|---|---|
| The guard | PreToolUse guardrail, read-only allowlist, fail-closed |
| Protected folders | Least privilege, integrity check (sha256), restore from a tag |
| The timer | Timeboxing (Shape Up), enforced per tool call |
| The relay | Context-window management, session handoff |
| The night | Unattended runs, token-budget pacing |
| The STATUS line | Agent heartbeat for an orchestrator |
| Her yes | Human-in-the-loop approval |
| The reviewer | LLM-as-judge, calibrated on human verdicts |
| The refusals log | Audit log |

None of these hooks is a prompt-injection filter (OWASP LLM01). They limit what a misled agent can do (OWASP LLM06, Excessive Agency).

## Run the tests

```
python -I tools/run_tests.py
```

Python standard library only. Each test writes only into its own temporary folder. Tested on Windows, Python 3.14.

<details>
<summary>Configuration (environment variables)</summary>

| Variable | Default | Used by |
|---|---|---|
| `GUARDRAILS_STATE_DIR` | `~/.claude-guardrails` | all |
| `GUARDRAILS_PROTECTED_PATHS` | `refs/approved,docs/story_bible` | guard |
| `GUARDRAILS_PROTECTED_NAMES` | `story_bible` | guard |
| `GUARDRAILS_HUMAN_ONLY` | `add_ref` | guard |
| `GUARDRAILS_RESTORE` | `git checkout protected-ok -- ...` | guard |
| `GUARDRAILS_ROLES` | `game,code,workshop,sound,video` | timer |
| `GUARDRAILS_TIMER_ALLOWED` | `journal.md,docs/memo_,docs/production.md` | timer |
| `GUARDRAILS_RELAY_THRESHOLD` | `150000` | relay |
| `GUARDRAILS_PRODUCTION` | `$CLAUDE_PROJECT_DIR/docs/production.md` | night |
| `GUARDRAILS_USAGE` | `<state>/usage.json` | night, continuous |

Other paths are listed at the top of each hook. Before publishing: `python -I tools/check_leaks.py`.
</details>

## Stack

Claude Code hooks, skills and sub-agents · Python standard library · a home-made orchestration (local dashboard, file mailboxes), no agent framework · Godot · Blender through MCP.

MIT, see [`LICENSE`](LICENSE).
