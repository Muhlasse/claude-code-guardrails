# claude-code-guardrails

How one person directs several Claude Code sessions on a game project, with guardrails that are code, not wishes.

The project is a first-person horror game demo in Godot. I am the only human. Several Claude Code sessions work on it
at the same time, each with a role (`game`, `code`, `workshop`, `sound`, `video`): the game session talks with me, the
others work in the background, and some of them keep working at night. Every rule that matters is enforced by a
**Claude Code hook** written in plain Python and covered by tests.

This repository is a cleaned-up copy of those hooks, their tests, three skills, one reviewer agent and the project
rules. Paths and names are configurable through environment variables; nothing here depends on my machine.

```
   human (me)
     |  talks to the game session, answers questions on a local dashboard
     v
   Claude Code sessions: game | code | workshop | sound | video
     |   every tool call / every end of reply goes through the hooks
     v
   +-------------------- .claude/settings.json ---------------------+
   | PreToolUse        guard.py      protected folders, no blender -b|
   |                   timer.py      time up -> deny work tools      |
   | PostToolUse       timer.py      15-min warning, "time up"       |
   |                   relay.py      context too big -> handoff note |
   | Stop              night.py      keep working until she wakes up |
   |                   continuous.py STATUS line -> continue or stop |
   |                   language.py   reply in her language           |
   | UserPromptSubmit  night.py --wake   her message ends the night  |
   +----------------------------------------------------------------+
     |  state files (JSON) in GUARDRAILS_STATE_DIR
     v
   local dashboard (not in this repo): timers, refusals log, relays, questions
```

## The hooks

Each hook reads the event JSON on stdin and answers the way Claude Code expects: exit code 2 with a reason on stderr,
a `permissionDecision: deny`, a `decision: block` with a reason, or `additionalContext`. The guard fails closed (any
error = refusal); the other hooks fail open (any error = they step aside), so a bug never jams a session.

### `guard.py` - PreToolUse guard on shell and Blender code
Prevents: any write into the protected folders (approved references, story bible). Near a protected path, only
read-only commands pass (`cat`, `ls`, `grep`, `git status/log/diff/show`, opening one image, an ffmpeg contact sheet
written elsewhere, the one git restore command); redirections (`>`), `$( )`, backticks and `Invoke-Expression` are
refused; a wildcard that could reach a protected folder (`rm docs/st*`) is refused while `wc -l docs/0*.md` passes.
It also refuses `blender -b` / `--background` (Blender is driven through MCP only), scripts reserved to the human, and
Blender Python that uses `subprocess` / `os.system` or writes near a protected path. Every refusal is appended to a
JSONL log. Known limit, written in the file: it reads text, so a script written to disk and then run escapes it; the
last line of defence is a sha256 fingerprint check plus a restore from a git tag.
[`hooks/guard.py`](hooks/guard.py) - test: [`hooks/tests/test_guard.py`](hooks/tests/test_guard.py) (68 checks,
including the real false positives it once had).

### `timer.py` - timeboxing
Prevents: working past the time chosen with the human. A session starts its timer (`--start game 90 "the door"`).
15 minutes before the end, PostToolUse tells the session once; when the time is up, PreToolUse denies `Edit`/`Write`
outside the wrap-up files, Blender MCP calls, shell commands that launch Godot or Blender, and new sub-agents. Reading,
asking the human and committing still pass. A session cannot restart a timer to keep going: only the human extends or
stops it. At night elapsed time does not block, but her "stop" still does.
[`hooks/timer.py`](hooks/timer.py) - test: [`hooks/tests/test_timer.py`](hooks/tests/test_timer.py) (28 checks).

### `relay.py` - context-window management, session handoff
Prevents: a conversation that grows past the "smart zone". Claude Code cannot type `/clear` by itself, so above
150k tokens (read from a per-session card that the status line keeps up to date) PostToolUse tells the session, once:
finish what you are doing, write a handoff note, then run `relay.py --ready <role>`. `--ready` refuses a missing note,
one older than 30 minutes or shorter than 200 bytes. The dashboard then closes the session and reopens a fresh one on
its note. Never at night.
[`hooks/relay.py`](hooks/relay.py) - test: [`hooks/tests/test_relay.py`](hooks/tests/test_relay.py) (15 checks).

### `night.py` - unattended night runs
Prevents: a night session that stops after 20 minutes, or that never stops. With a marker file written after the
human's "ok", the Stop hook sends the session back to its queue until she wakes up (her first real message, or the
machine back in day mode). Messages that look like hers but are not (sub-agent reports, other sessions, task
notifications) do not count as a wake-up, nor do her messages in the first 20 minutes. It paces quota: weekly usage may
not go above a straight line from 0 % to 100 % over the week (or 95 % of the 5-hour window); above it the session
pauses and a background `--wait` resumes it. Three replies without progress = a pause, not a stop (20 at most). A
"nothing left to do" summary is refused until it names every open task of the role and contains the "Ahead" and
"Further" sections. Hard stops: 16 hours, 200 relaunches. An "away" mode does the same in the daytime.
[`hooks/night.py`](hooks/night.py) - test: [`hooks/tests/test_night.py`](hooks/tests/test_night.py) (36 checks).

### `continuous.py` - background sessions that do not stall silently
Prevents: a background session that stops without anyone noticing. Every reply ends with one line,
`STATUS: continue | waiting for her choice | waiting for <session> | nothing - <detail>`. On `continue` the Stop hook
sends it back to work; the state is written for the dashboard. Background roles that forget the line get one nudge.
Never above the quota line, and 40 `continue` in a row = pause. During a night, `night.py` is in charge.
[`hooks/continuous.py`](hooks/continuous.py) - test: [`hooks/tests/test_continuous.py`](hooks/tests/test_continuous.py) (19 checks).

### `language.py` - replies in the human's language
Prevents: progress messages in English when she works in French (a written rule was not enough). The Stop hook counts
common English and French words in the replies since her last message (code and links ignored) and, if English wins,
blocks once and asks for the content again in French. `stop_hook_active` stops it from looping.
[`hooks/language.py`](hooks/language.py) - test: [`hooks/tests/test_language.py`](hooks/tests/test_language.py) (10 checks).

### Permissions
[`examples/settings.json`](examples/settings.json) wires the hooks and adds what the permission system can do by
itself: bypass mode disabled, `Edit`/`Write` denied on the protected folders, the Blender MCP `generate_3d` tool denied
(no generative model for assets), asset imports always asked.

## Skills, agent, rules
- [`skills/start`](skills/start/SKILL.md) and [`skills/end`](skills/end/SKILL.md): the session ritual (state summary,
  weekly rules review on Mondays, journal entry, "tests never weakened" check, commit through one script).
- [`skills/improve`](skills/improve/SKILL.md): after a mixed verdict, a scoring grid written before making anything,
  3 candidates, evidence per score; the human's verdict decides and is recorded for next time.
- [`agents/reviewer.md`](agents/reviewer.md): a read-only agent that predicts whether an attempt will be refused,
  based on the human's past verdicts, with its own calibration notes; it is dropped if wrong more than half the time.
- [`rules/CLAUDE.md`](rules/CLAUDE.md): the project rules - one rule in, one out; size caps; weekly review; a mechanic
  is played before it is judged; pre-mortem (Gary Klein); fixed time (Shape Up); human in the loop for anything that
  costs, is approved or is published; no generative model for assets; tests never weakened.

## What we call it | Industry term

| What we call it | Industry term |
|---|---|
| The guard | PreToolUse guard, guardrails, allowlist of read-only commands, fail-closed policy |
| Protected folders | Least privilege, deny rules, integrity check (sha256) with restore from a git tag |
| The timer | Timeboxing (Shape Up appetite), enforced at the tool-call level |
| The relay | Context-window management, session handoff (summary note, then a fresh session) |
| The night | Unattended runs, token-budget pacing, rate-limit aware scheduling |
| The STATUS line | Agent self-reported state, heartbeat for an orchestrator |
| Her yes | Human-in-the-loop (HITL) approval |
| The reviewer | LLM-as-judge, calibrated against human verdicts |
| The refusals log | Audit log, observability |

No hook here is a prompt-injection filter (OWASP LLM01). What they do is limit what a misled agent can do (OWASP
LLM06, Excessive Agency): even a hijacked session cannot write into the protected folders through the shell, and
`night.py` does not trust a message as the human's just because it arrives in the user turn.

## Run the tests

```
python -I tools/run_tests.py
```

Python standard library only, no pytest. Each test file can also run alone (`python -I hooks/tests/test_guard.py`)
and writes only into its own temporary folder. Current result: 176 checks, 0 failures (tested on Windows, Python 3.14).

Before publishing: `python -I tools/check_leaks.py` (fails on any private word; the private list stays local and git-ignored).

## Configuration

| Variable | Default | Used by |
|---|---|---|
| `GUARDRAILS_STATE_DIR` | `~/.claude-guardrails` | all (timer, night, relay, continuous state, refusals log) |
| `GUARDRAILS_PROTECTED_PATHS` | `refs/approved,docs/story_bible` | guard |
| `GUARDRAILS_PROTECTED_NAMES` | `story_bible` | guard |
| `GUARDRAILS_HUMAN_ONLY` | `add_ref` | guard |
| `GUARDRAILS_RESTORE` | `git checkout protected-ok -- ...` | guard |
| `GUARDRAILS_ROLES` | `game,code,workshop,sound,video` | timer |
| `GUARDRAILS_TIMER_ALLOWED` | `journal.md,docs/memo_,docs/production.md` | timer |
| `GUARDRAILS_RELAY_THRESHOLD` | `150000` | relay |
| `GUARDRAILS_PRODUCTION` | `$CLAUDE_PROJECT_DIR/docs/production.md` | night |
| `GUARDRAILS_USAGE` | `<state>/usage.json` (`{"limits": {"seven_day": ..., "five_hour": ...}}`) | night, continuous |

The other paths (`*_DIR`, `GUARDRAILS_AWAY`, `GUARDRAILS_WAKE_COMMAND`...) are listed at the top of each hook.

## Stack
Claude Code hooks (PreToolUse, PostToolUse, Stop, UserPromptSubmit), skills and sub-agents; Python standard library;
a home-made orchestration (a local dashboard and file-based mailboxes, not in this repository), no agent framework.
Game: Godot. 3D: Blender through MCP.

## License
MIT, see [`LICENSE`](LICENSE).
