"""PreToolUse guard (Bash, PowerShell, Blender MCP execute_blender_code).

Exit 0 = the command runs; exit 2 = refused (the reason goes to stderr, Claude Code shows it to the agent).
When in doubt (unreadable JSON, exception), it refuses.

Known limits: it reads text. A script written to disk then run, a `cd` spread over several steps, or a path
assembled inside Python escape it. The real last line of defence is a fingerprint check of the protected folders
(sha256 list) plus a restore from a git tag (RESTORE_COMMAND below).

Configuration (environment variables, all optional):
  GUARDRAILS_PROTECTED_PATHS  comma-separated folders agents may only READ (default: refs/approved,docs/story_bible)
  GUARDRAILS_PROTECTED_NAMES  folder names refused even without their parent path (default: story_bible)
  GUARDRAILS_HUMAN_ONLY       comma-separated script names only the human may run (default: add_ref)
  GUARDRAILS_RESTORE          the one write command allowed on protected folders (a git restore from a tag)
  GUARDRAILS_REFUSALS         JSONL log of refusals (default: ~/.claude-guardrails/guards/refusals.jsonl)
"""
import json
import os
import re
import sys


def _list(name, default):
    return [x.strip().strip("/\\") for x in os.environ.get(name, default).split(",") if x.strip()]


PROTECTED_PATHS = _list("GUARDRAILS_PROTECTED_PATHS", "refs/approved,docs/story_bible")
PROTECTED_NAMES = _list("GUARDRAILS_PROTECTED_NAMES", "story_bible")
HUMAN_ONLY = _list("GUARDRAILS_HUMAN_ONLY", "add_ref")
RESTORE_COMMAND = os.environ.get(
    "GUARDRAILS_RESTORE", "git checkout protected-ok -- refs/approved refs/approved.sha256 docs/story_bible")
STATE_DIR = os.environ.get("GUARDRAILS_STATE_DIR", os.path.join(os.path.expanduser("~"), ".claude-guardrails"))


def _path_pattern(p):
    """refs/approved -> refs[\\/]+approved (either slash, repeated)."""
    return r"[\\/]+".join(re.escape(s) for s in re.split(r"[\\/]+", p))


PROTECTED = re.compile("|".join([_path_pattern(p) for p in PROTECTED_PATHS] +
                                [re.escape(n) for n in PROTECTED_NAMES]) or r"(?!)", re.I)
# A wildcard right after a protected folder's parent (refs/*, docs/b*) is refused only if it can reach the protected
# name, i.e. if the text before the wildcard is a prefix of that name (refs/app*, docs/*, docs/[s]...).
# docs/0*.md passes ("0" is not a prefix of "story_bible").
TARGETS = {}
for _p in PROTECTED_PATHS:
    _parent, _, _name = re.sub(r"[\\/]+", "/", _p).rpartition("/")
    if _parent:
        TARGETS.setdefault(_parent.lower(), []).append(_name.lower())
WILDCARD = re.compile(r"(" + "|".join(_path_pattern(p) for p in TARGETS) + r")[\\/]+([^\s\\/'\"*?\[]*)[*?\[]", re.I) \
    if TARGETS else None


def targets_protected(command):
    if PROTECTED.search(command):
        return True
    if WILDCARD:
        for m in WILDCARD.finditer(command):
            parent = re.sub(r"[\\/]+", "/", m.group(1)).lower()
            if any(n.startswith(m.group(2).lower()) for n in TARGETS.get(parent, [])):
                return True
    return False


READ_FIRST_WORD = {"get-content", "cat", "type", "ls", "dir", "get-childitem", "select-string",
                   "grep", "rg", "test-path", "get-item", "get-filehash",
                   "cd", "set-location", "head", "tail", "cut", "wc"}
READ_GIT = {"status", "log", "diff", "show"}
OPEN = {"start-process", "saps", "start", "ii", "invoke-item"}
IMAGE = re.compile(r"\.(jpe?g|png|webp|gif|bmp)$", re.I)
DANGER = re.compile(r">|\$\(|`|\biex\b|invoke-expression", re.I)
BACKGROUND = re.compile(r"(?<![^\s'\"])-b\b|--background", re.I)
BLENDER = re.compile(r"^blender(\.exe)?$", re.I)

CODE_FORBIDDEN = re.compile(r"subprocess|os\.system|os\.popen")
CODE_WRITE = re.compile(
    r"os\.remove|unlink|rmdir|shutil|rename|replace|write_text|write_bytes"
    r"|save_as_mainfile|save_mainfile|save_render|image\.save|\.save\(|filepath_raw"
    r"|write_still|chmod"
    r"|open\([^)]*['\"][rwaxbt]*[wax+][rwaxbt+]*['\"]",
)


def outside_quotes(command):
    """Split on ; | && || and newlines, but not inside quotes
    (a grep pattern 'a|b' is one argument, not a pipe).
    Escaped quote (\\" or \\') or a quote left open: split everywhere, as before (stricter)."""
    naive = re.split(r"&&|\|\||[;|\n\r]", command)
    if re.search(r"\\['\"]", command):
        return naive
    res, cur, q, i = [], "", None, 0
    while i < len(command):
        c = command[i]
        if q:
            if c == q:
                q = None
            cur += c
        elif c in "'\"":
            q = c
            cur += c
        elif command.startswith(("&&", "||"), i):
            res.append(cur)
            cur = ""
            i += 1
        elif c in ";|\n\r":
            res.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    if q:
        return naive
    res.append(cur)
    return res


def pieces(command):
    """Split on ; | && || newlines, and on & except at the start of a piece."""
    res = []
    for big in outside_quotes(command):
        big = big.strip()
        head = ""
        if big.startswith("&"):              # PowerShell call operator
            head, big = "& ", big[1:].lstrip()
        parts = big.split("&")
        parts[0] = head + parts[0]
        res.extend(p.strip() for p in parts if p.strip())
    return res


def words(piece):
    """Simple word split, quotes respected."""
    return [a or b or c for a, b, c in re.findall(r'"([^"]*)"|\'([^\']*)\'|(\S+)', piece)]


def starts_blender(piece):
    m = words(piece)
    if m and m[0] == "&":
        m = m[1:]
    if m and m[0].lower() in ("start-process", "start", "saps"):
        m = [x for x in m[1:] if x.lower() != "-filepath"]
    if not m:
        return False
    name = re.split(r"[\\/]", m[0])[-1]
    return bool(BLENDER.match(name))


def opens_one_image(m):
    """Opening ONE image on screen (default viewer) is read-only. No other argument."""
    if m[0].lower() not in OPEN:
        return False
    args = [x for x in m[1:] if x.lower() != "-filepath"]
    return len(args) == 1 and bool(IMAGE.search(args[0]))


def measures_images(m):
    """tools/measure_values.py on images only: it reads them and prints numbers.
    Without --small (its only option that writes) and without any other argument."""
    if len(m) < 3 or not re.search(r"(^|[\\/])python(\.exe)?$", m[0], re.I):
        return False
    if not re.search(r"(^|[\\/])tools[\\/]measure_values\.py$", m[1], re.I):
        return False
    return all(IMAGE.search(x) for x in m[2:])


def ffmpeg_contact_sheet(m):
    """ffmpeg READING protected images to build a contact sheet elsewhere. Each protected path must follow a -i and be
    an image; the output (last argument) is an image outside the protected folders. No other protected path."""
    if len(m) < 4 or not re.search(r"(^|[\\/])ffmpeg(\.exe)?$", m[0], re.I):
        return False
    out = m[-1]
    if targets_protected(out) or not IMAGE.search(out):
        return False
    for i, x in enumerate(m[1:-1], start=1):
        if targets_protected(x) and not (m[i - 1] == "-i" and IMAGE.search(x)):
            return False
    return True


def is_read(piece):
    if " ".join(piece.split()) == RESTORE_COMMAND:
        return True
    m = words(piece)
    if not m:
        return True
    if m[0].lower() in READ_FIRST_WORD or opens_one_image(m) or measures_images(m) or ffmpeg_contact_sheet(m):
        return True
    return m[0].lower() == "git" and len(m) > 1 and m[1].lower() in READ_GIT


def judge_command(command):
    for script in HUMAN_ONLY:
        if re.search(re.escape(script), command, re.I):
            return f"{script} is run only by the human (with ! or in a separate terminal)"
    liste = pieces(command)
    for m in liste:
        if starts_blender(m) and BACKGROUND.search(m):
            return "never blender -b / --background: Blender is driven through MCP"
    if targets_protected(command):
        for m in liste:
            if DANGER.search(m):
                return f"protected folder: redirection or indirect execution forbidden ({m!r})"
            if not is_read(m):
                return f"protected folder: read-only ({m!r})"
    return None


def judge_code(code):
    if CODE_FORBIDDEN.search(code):
        return "Blender code: subprocess / os.system / os.popen forbidden"
    if PROTECTED.search(code) and CODE_WRITE.search(code):
        return "Blender code: write near a protected path"
    return None


def judge(data):
    tool_input = data["tool_input"]
    tool = data.get("tool_name", "")
    if tool in ("Bash", "PowerShell"):
        return judge_command(tool_input["command"])
    if tool.endswith("execute_blender_code"):
        return judge_code(tool_input["code"])
    return None


def log_refusal(guard, data, reason):
    """One line per refusal in the refusals log (read by the dashboard).
    Append only: a write failure never changes the guard's decision."""
    try:
        import datetime
        f = os.environ.get("GUARDRAILS_REFUSALS", os.path.join(STATE_DIR, "guards", "refusals.jsonl"))
        os.makedirs(os.path.dirname(f), exist_ok=True)
        line = {"when": datetime.datetime.now().isoformat(timespec="seconds"), "guard": guard,
                "session": str((data or {}).get("session_id", ""))[:12], "tool": str((data or {}).get("tool_name", "")),
                "reason": str(reason)[:300]}
        with open(f, "a", encoding="utf-8") as h:
            h.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main():
    code, reason, data = 2, "unknown error", {}
    try:
        sys.stderr.reconfigure(encoding="utf-8")
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        reason = judge(data)
        code = 2 if reason else 0
    except Exception as e:  # not BaseException: sys.exit must stay outside the try
        code, reason = 2, f"guard.py failed, refusing to be safe: {type(e).__name__}: {e}"
    if code:
        print(f"[guard] {reason}", file=sys.stderr)
        log_refusal("guard", data if isinstance(data, dict) else {}, reason)
    sys.exit(code)


if __name__ == "__main__":
    main()
