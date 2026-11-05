# The universal timer (timeboxing). The fixed-time rule (Ryan Singer, Shape Up): each piece of work gets a time chosen
# WITH the human; when it is up, we stop without extending and ask her again. This guard makes it hold for real, for
# every session and its sub-agents (her words: "nobody manages to respect the times").
#
# For a session (the time is chosen WITH her first):
#   python -I hooks/timer.py --start game 90 "the door in the dark"
#   python -I hooks/timer.py --done game        work finished early: release the timer
#   python -I hooks/timer.py --status           all timers
# Only she extends or stops it (the dashboard's "+30 min" and "stop" buttons): there is no --extend here.
#
# The guard (wired in .claude/settings.json):
#   PreToolUse  : time up -> denies what moves the work forward (Edit/Write outside the wrap-up files, Blender, launching
#                 Godot, new sub-agents); the rest passes (reading, talking to her, the JOURNAL, the night queue);
#   PostToolUse : a quarter of an hour before the end, then once the time is up, tells the session.
# At night there is no timer (her rule: "at night, no timer; the only limit is the quota"): while the session's night
#   marker exists (<NIGHT_DIR>/running_<role>.json, not in away mode), elapsed time blocks nothing; only her "stop"
#   click still blocks. Away mode keeps its time.
# Files: <TIMER_DIR>/<role>.json
#   {"role", "work", "start", "minutes", "end", "state": "running"|"done"|"stopped", "said": [...]}
import json, os, re, sys, datetime

STATE_DIR = os.environ.get('GUARDRAILS_STATE_DIR', os.path.join(os.path.expanduser('~'), '.claude-guardrails'))
FOLDER = os.environ.get('GUARDRAILS_TIMER_DIR', os.path.join(STATE_DIR, 'timer'))
ROLES = tuple(r.strip() for r in os.environ.get('GUARDRAILS_ROLES', 'game,code,workshop,sound,video').split(',') if r.strip())
# what may still be written when the time is up: the wrap-up, not the work itself
ALLOWED = tuple(x.strip().lower() for x in os.environ.get(
    'GUARDRAILS_TIMER_ALLOWED', 'journal.md,docs/memo_,docs/production.md').split(',') if x.strip()) \
    + (STATE_DIR.replace('\\', '/').lower().rstrip('/') + '/',)


def now():
    return datetime.datetime.now().replace(microsecond=0)


def read(role):
    try:
        return json.load(open(os.path.join(FOLDER, f'{role}.json'), encoding='utf-8-sig'))
    except Exception:
        return None


def write(m):
    os.makedirs(FOLDER, exist_ok=True)
    f = os.path.join(FOLDER, f"{m['role']}.json")
    json.dump(m, open(f + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(f + '.tmp', f)


def end_of(m):
    try:
        return datetime.datetime.fromisoformat(str(m.get('end')))
    except Exception:
        return None


def minutes_left(m):
    f = end_of(m)
    return None if f is None else (f - now()).total_seconds() / 60


def expired(m):
    """Time is up: the hour has passed, or she clicked "stop"."""
    if not m or m.get('state') == 'done':
        return False
    if m.get('state') == 'stopped':
        return True
    r = minutes_left(m)
    return r is not None and r <= 0


def start(role, minutes, work):
    role = role.lower()
    if role not in ROLES:
        return f'Unknown role: {role}.'
    m = read(role)
    if expired(m):
        return (f"Refused: the time for \"{m.get('work')}\" is up and she has not extended it. A timer is not restarted "
                "to keep going: write your wrap-up and ask her again (she extends or stops it from the dashboard).")
    if m and m.get('state') == 'running':
        return (f"Refused: \"{m.get('work')}\" is still running ({minutes_left(m):.0f} min left). "
                f"Finished early? --done {role}, then start again.")
    try:
        minutes = int(minutes)
    except Exception:
        return 'Time is given in minutes (a number).'
    if not 5 <= minutes <= 600:
        return 'Between 5 and 600 minutes.'
    d = now()
    write({'role': role, 'work': str(work)[:200], 'start': d.isoformat(), 'minutes': minutes,
           'end': (d + datetime.timedelta(minutes=minutes)).isoformat(), 'state': 'running', 'said': []})
    return f"Timer started: {role.upper()}, \"{work}\", {minutes} min (ends at {(d + datetime.timedelta(minutes=minutes)):%H:%M}). The dashboard shows it."


def done(role):
    m = read(role.lower())
    if not m:
        return 'No timer.'
    m['state'] = 'done'; m['released'] = now().isoformat()
    write(m)
    return f"Timer released: \"{m.get('work')}\"."


# --- the guard ---
def role_of(data):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import night
        return (data.get('role') or night.role_from_session(data.get('session_id', '')) or '').lower()
    except Exception:
        return (data.get('role') or '').lower()


def path_allowed(p):
    p = str(p or '').replace('\\', '/').lower()
    return any(x in p for x in ALLOWED)


def moves_work_forward(data):
    """Does this tool call move the work forward (to deny once the time is up)?"""
    tool = data.get('tool_name', '')
    ti = data.get('tool_input') or {}
    if tool in ('Edit', 'Write', 'NotebookEdit', 'MultiEdit'):
        return not path_allowed(ti.get('file_path') or ti.get('notebook_path'))
    if re.match(r'mcp__blender\d*__(execute_blender_code|import_asset)', tool):
        return True
    if tool in ('Bash', 'PowerShell'):
        c = str(ti.get('command', '')).lower()
        if 'timer.py' in c or 'commit.ps1' in c:
            return False
        return bool(re.search(r'godot|blender', c))
    if tool == 'Agent':
        return True   # no new sub-agent to carry on quietly
    return False


def time_up_message(m):
    when = 'she clicked "stop"' if m.get('state') == 'stopped' else f"{m.get('minutes')} min, ended at {end_of(m):%H:%M}"
    return (f"⏱ TIME UP for \"{m.get('work')}\" ({when}). The fixed-time rule: we stop without extending. "
            "Do not make a new version. Write what is done and what is left (JOURNAL, your queue or report file), "
            "then ask her again: she extends (+30 min) or stops from the dashboard. Anything that changes the game is blocked.")


def log_refusal(guard, data, reason):
    """One line per refusal in the refusals log (read by the dashboard).
    Append only: a write failure never changes the guard's decision."""
    try:
        f = os.environ.get('GUARDRAILS_REFUSALS', os.path.join(STATE_DIR, 'guards', 'refusals.jsonl'))
        os.makedirs(os.path.dirname(f), exist_ok=True)
        line = {'when': datetime.datetime.now().isoformat(timespec='seconds'), 'guard': guard,
                'session': str((data or {}).get('session_id', ''))[:12], 'tool': str((data or {}).get('tool_name', '')),
                'reason': str(reason)[:300]}
        with open(f, 'a', encoding='utf-8') as h:
            h.write(json.dumps(line, ensure_ascii=False) + '\n')
    except Exception:
        pass


NIGHT = os.environ.get('GUARDRAILS_NIGHT_DIR', os.path.join(STATE_DIR, 'night'))


def is_night(role):
    """The session works at night (night guard marker, night mode and not away)."""
    try:
        t = json.load(open(os.path.join(NIGHT, f'running_{role}.json'), encoding='utf-8-sig'))
    except Exception:
        return False
    return isinstance(t, dict) and t.get('mode') != 'away'


def night_free(role, m):
    """At night, elapsed time does not count; her "stop" always does."""
    return bool(m) and m.get('state') != 'stopped' and is_night(role)


def pre(data):
    role = role_of(data)
    m = read(role)
    if night_free(role, m):
        return None
    if expired(m) and moves_work_forward(data):
        log_refusal('timer', data, f"time up: {m.get('work')}")
        return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                       'permissionDecisionReason': time_up_message(m)}}
    return None


def post(data):
    role = role_of(data)
    m = read(role)
    if not m or m.get('state') == 'done' or night_free(role, m):
        return None
    said = m.setdefault('said', [])
    if expired(m):
        key = 'up'
    else:
        r = minutes_left(m)
        key = 'quarter' if r is not None and r <= 15 else ''
    if not key or key in said:
        return None
    said.append(key); write(m)
    if key == 'quarter':
        text = (f"⏱ Only {minutes_left(m):.0f} min left for \"{m.get('work')}\". Finish what is in progress, "
                "open nothing new, prepare what you will show her.")
    else:
        text = time_up_message(m)
    return {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': text}}


def status():
    out = []
    for r in ROLES:
        m = read(r)
        if m and m.get('state') != 'done':
            r_ = minutes_left(m)
            out.append(f"{r.upper()}: \"{m.get('work')}\" - " + ('TIME UP' if expired(m) else f'{r_:.0f} min left'))
    return '\n'.join(out) or 'No timer running.'


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if '--start' in a:
        i = a.index('--start')
        if len(a) < i + 4:
            print('Usage: --start <role> <minutes> "<work>"'); sys.exit(1)
        print(start(a[i + 1], a[i + 2], ' '.join(a[i + 3:])))
    elif '--done' in a:
        print(done(a[a.index('--done') + 1]))
    elif '--status' in a:
        print(status())
    elif '--pre' in a or '--post' in a:
        try:
            data = json.loads(sys.stdin.buffer.read().decode('utf-8', 'replace') or '{}')
            r = pre(data) if '--pre' in a else post(data)
        except Exception:
            sys.exit(0)   # a timer error never jams a session
        if r:
            print(json.dumps(r, ensure_ascii=True))
    else:
        print(open(__file__, encoding='utf-8').read().split('import json')[0])
