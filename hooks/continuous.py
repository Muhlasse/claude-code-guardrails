# Continuous mode (Stop hook): her choice, "let them move forward without me whenever they can, and stop pausing
# forever without anyone seeing it".
# A session stops at the end of every reply. So it ends every report with ONE line:
#   STATUS: continue - <what it does now>               -> the guard sends it straight back to work
#   STATUS: waiting for her choice - <dashboard question> -> normal stop, the dashboard shows "waiting for your choice"
#   STATUS: waiting for <session> - <what>              -> normal stop, "waiting for GAME"; the watcher relaunches it later
#   STATUS: nothing - <why nothing is doable any more>  -> normal stop
# The guard writes this state to <CONTINUOUS_DIR>/<role>.json; the dashboard shows it on each session's card and its
# watcher nudges (via the mailbox) a session that stopped without a reason.
# Safeguards: never above the quota line (the same as at night); 40 "continue" in a row = pause, the watcher resumes
# later; during /night, night.py is in charge (this guard does nothing).
# The background roles (MUST_WRITE) must write the line (one nudge if forgotten); the human-facing sessions talk with
# her: without a line they are "free" and nothing relaunches them.
import json, os, re, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import night   # find_role, above_line (the quota line)

STATE_DIR = os.environ.get('GUARDRAILS_STATE_DIR', os.path.join(os.path.expanduser('~'), '.claude-guardrails'))
CONTINUOUS = os.environ.get('GUARDRAILS_CONTINUOUS_DIR', os.path.join(STATE_DIR, 'continuous'))
MUST_WRITE = tuple(r.strip() for r in os.environ.get('GUARDRAILS_MUST_WRITE', 'code,sound,video').split(',') if r.strip())
EXEMPT = tuple(r.strip() for r in os.environ.get('GUARDRAILS_EXEMPT_ROLES', '').split(',') if r.strip())
MAX_CONTINUES = 40


def last_text(data):
    """The text of the last reply: given by Claude Code, otherwise read from the end of the transcript."""
    t = data.get('last_assistant_message')
    if isinstance(t, str) and t.strip():
        return t
    p = data.get('transcript_path') or ''
    try:
        size = os.path.getsize(p)
        with open(p, 'rb') as f:
            f.seek(max(0, size - 600_000))
            lines = f.read().decode('utf-8', 'ignore').splitlines()
    except Exception:
        return ''
    for l in reversed(lines):
        if '"type":"assistant"' not in l:
            continue
        try:
            o = json.loads(l)
        except Exception:
            continue
        c = (o.get('message') or {}).get('content')
        if isinstance(c, list):
            txt = '\n'.join(x.get('text', '') for x in c if isinstance(x, dict) and x.get('type') == 'text').strip()
            if txt:
                return txt
        elif isinstance(c, str) and c.strip():
            return c
    return ''


def read_status(text):
    """(state, detail, who) from the last "STATUS: ..." line, or (None, '', '')."""
    m = None
    for m in re.finditer(r'^[\s>*_`-]*STATUS\s*:\s*(.+?)\s*[*_`]*\s*$', text or '', re.M | re.I):
        pass
    if not m:
        return None, '', ''
    line = m.group(1).strip()
    parts = re.split(r'\s+[—–-]\s+', line, maxsplit=1)
    head = parts[0].lower().strip(' .:')
    detail = parts[1].strip() if len(parts) > 1 else ''
    if head.startswith('continue'):
        return 'continue', detail or head[8:].strip(' :'), ''
    if head.startswith(('nothing', 'done')):
        return 'nothing', detail, ''
    am = re.match(r'waiting(?:\s+(?:for|on))?\s+(.*)', head)
    if am:
        what = am.group(1)
        if re.match(r"(her|his|their|your|my)\b|(the user|user|the human|human)\b", what):
            return 'user', detail or what, ''
        who = re.sub(r'^(the session|session|the)\s*', '', what).split()[0] if what.strip() else '?'
        return 'session', detail or what, who.strip(" .:,'").upper()
    return 'other', line, ''


def write_state(role, d):
    try:
        os.makedirs(CONTINUOUS, exist_ok=True)
        f = os.path.join(CONTINUOUS, f'{role}.json')
        json.dump(d, open(f + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False)
        os.replace(f + '.tmp', f)
    except Exception:
        pass


def read_previous(role):
    try:
        return json.load(open(os.path.join(CONTINUOUS, f'{role}.json'), encoding='utf-8-sig'))
    except Exception:
        return {}


def decide(data, now=None, quota=None):
    """Stop hook. Returns (block, reason). Separate from main for the tests."""
    now = now or datetime.datetime.now()
    role = night.find_role(data)
    if not role or role in EXEMPT:
        return False, ''
    if os.path.exists(os.path.join(night.NIGHT, f'running_{role}.json')):
        return False, ''   # /night running: night.py is in charge
    previous = read_previous(role)
    state, detail, who = read_status(last_text(data))
    base = {'role': role, 'when': now.isoformat(timespec='seconds'), 'session': data.get('session_id', '')}

    if state == 'continue':
        too_much = quota if quota is not None else night.above_line()
        recent = False
        try:
            recent = (now - datetime.datetime.fromisoformat(previous.get('when', ''))).total_seconds() < 1800
        except Exception:
            pass
        continues = int(previous.get('continues', 0)) + 1 if previous.get('state') == 'continue' and recent else 1
        if too_much:
            write_state(role, {**base, 'state': 'quota', 'detail': detail, 'why': too_much, 'continues': 0})
            return False, ''
        if continues > MAX_CONTINUES:
            write_state(role, {**base, 'state': 'pause', 'detail': detail, 'continues': 0})
            return False, ''
        write_state(role, {**base, 'state': 'continue', 'detail': detail, 'continues': continues})
        return True, (f"Continuous mode: your STATUS line says \"continue - {detail}\". She wants you to move forward without her "
                      "whenever you can: do it now, without asking her for a green light. Anything to be judged goes through the "
                      "dashboard (without -Wait). At the end, write your STATUS line again (continue / waiting for her choice / "
                      "waiting for <session> / nothing).")

    if state is None:
        if role not in MUST_WRITE:
            write_state(role, {**base, 'state': 'free', 'detail': ''})
            return False, ''
        missed = int(previous.get('missed', 0)) if previous.get('state') == 'no_status' else 0
        write_state(role, {**base, 'state': 'no_status', 'detail': '', 'missed': missed + 1})
        if missed >= 1:
            return False, ''   # already nudged once for this: the dashboard's watcher takes over
        return True, ("Continuous mode: end your reply with a STATUS line, alone on its line, so the dashboard knows where you "
                      "stand: \"STATUS: continue - <what you do now>\" if you can move forward without her (then do it), "
                      "\"STATUS: waiting for her choice - <question>\", \"STATUS: waiting for <session> - <what>\" or "
                      "\"STATUS: nothing - <why>\".")

    write_state(role, {**base, 'state': state, 'detail': detail, 'who': who})
    return False, ''


if __name__ == '__main__':
    try:
        data = json.loads(sys.stdin.buffer.read().decode('utf-8', 'replace') or '{}')   # UTF-8: otherwise non-ASCII arrives garbled (cp1252)
    except Exception:
        sys.exit(0)
    try:
        block, reason = decide(data)
    except Exception:
        sys.exit(0)   # a guard error must never jam a session
    if block:
        print(json.dumps({'decision': 'block', 'reason': reason}, ensure_ascii=True))
    sys.exit(0)
