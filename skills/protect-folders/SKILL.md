---
name: protect-folders
description: Make chosen folders read-only for Claude Code agents. Installs a tested PreToolUse hook (Python standard library, no network) that lets shell commands read those folders but refuses anything that could write, move or delete in them, and adds matching Edit/Write deny rules. Use when the user wants to protect source data, assets, secrets or reference files from an agent.
license: MIT
---

# protect-folders

Turns a few folders into **read-only for agents**. The human keeps full access.

Two layers:
1. **Permissions** (`Edit` / `Write` denied on those folders): Claude Code's own rules.
2. **A guard hook** (`scripts/guard.py`) on every `Bash` and `PowerShell` call: near a protected path, only read-only
   commands pass (`cat`, `ls`, `grep`, `git status/log/diff/show`...). Redirections (`>`), `$( )`, backticks,
   `Invoke-Expression`, and wildcards that could reach a protected folder are refused. Any error means "no" (fails closed).

The guard is taken from the `claude-code-guardrails` repository on GitHub, where it runs every day and has its own
tests (`hooks/tests/test_guard.py`).

## Steps

1. **Ask the human** which folders to protect (paths relative to the project root, e.g. `data/raw`, `secrets`).
   Do not guess. Confirm the list back in one line.
2. **Copy** `scripts/guard.py` from this skill to `.claude/hooks/guard.py` in the project.
3. **Merge** into `.claude/settings.json` (create it if missing). Never overwrite existing keys: append to existing
   lists, keep the user's other hooks and rules. The block to merge is in `reference/settings.example.json`:
   - `env.GUARDRAILS_PROTECTED_PATHS`: the folders, comma-separated (`data/raw,secrets`).
   - `env.GUARDRAILS_PROTECTED_NAMES`, `env.GUARDRAILS_HUMAN_ONLY`, `env.GUARDRAILS_RESTORE`: set to `""`
     (they are for the original project; empty turns them off).
   - `permissions.deny`: `Edit(/<folder>/**)` and `Write(/<folder>/**)` for each folder.
   - `hooks.PreToolUse`: matcher `Bash|PowerShell`, command
     `python -I "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.py"`. Use `python3` instead of `python` if that is the
     interpreter on this machine (check with `python3 --version`).
4. **Check** the guard by piping two fake tool calls into it, with the folders set for this test only:
   - a read must pass (exit code 0):
     `{"tool_name":"Bash","tool_input":{"command":"ls data/raw"}}`
   - a delete must be refused (exit code 2, reason on stderr):
     `{"tool_name":"Bash","tool_input":{"command":"rm -rf data/raw"}}`

   Example (bash): `echo '<json>' | GUARDRAILS_PROTECTED_PATHS="data/raw" GUARDRAILS_PROTECTED_NAMES="" GUARDRAILS_HUMAN_ONLY="" python -I .claude/hooks/guard.py; echo $?`

   If either result is wrong, stop and tell the human; do not loosen the guard.
5. **Tell the human**, in a few lines:
   - which folders are protected, and that the settings apply after Claude Code is restarted;
   - the limits below;
   - that refusals are logged to `~/.claude-guardrails/guards/refusals.jsonl` (local file, change it with
     `GUARDRAILS_REFUSALS`).

## Limits (say them, do not hide them)

- The guard reads command **text**. A script written to disk and then run, a `cd` spread over several steps, or a path
  built inside Python escapes it. It is a seatbelt, not a sandbox.
- It does not protect against the human, and it is not a prompt-injection filter. It limits what a misled agent can
  do (OWASP LLM06, Excessive Agency).
- A real last line of defence: a sha256 list of the protected files checked at session start, and a git tag to restore
  from.
- When in doubt, the guard refuses. A false refusal is shown to the agent with its reason; the human can then run the
  command themselves.

## What this skill does not do

- No network access, no package to install, no account. Python standard library only.
- It does not change files outside `.claude/` in the project.
