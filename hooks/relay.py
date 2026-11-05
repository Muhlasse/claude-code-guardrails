# The relay: an automatic /clear (context-window management, session handoff).
# Claude Code cannot type /clear by itself (neither a hook nor a message from another session can). So the same thing
# is done another way: the session writes where it stands, says "ready", and the dashboard closes it and opens a fresh
# one with the same name, which reads its note before /start. The goal is to stay in the "smart zone" (a conversation
# that grows too long reasons less well).
#
#   PostToolUse (--post) : the conversation passes THRESHOLD tokens (read from the session directory that the status
#                          line keeps up to date) -> once per conversation, the relay instruction. Never at night.
#   python -I hooks/relay.py --ready <role>
#                          the session has written its note (<RELAY_DIR>/<role>.md) and declares itself ready.
#   python -I hooks/relay.py --status
#
# The dashboard waits until the session has been idle for a minute, then runs a restart script, which refuses if Godot
# is running under the session, otherwise closes it and reopens it. (The dashboard and that script are not in this repo.)
# Files: <RELAY_DIR>/<role>.json  {"state": "told"|"ready"|"running"|"done"|"refused", "session", "when", "reason"}
#        <RELAY_DIR>/<role>.md    the handoff note (written by the session)
#        <DIRECTORY_DIR>/*.json   one card per live session: {"sessionId", "name", "context"} (context = tokens used)
import json, os, sys, datetime

STATE_DIR = os.environ.get('GUARDRAILS_STATE_DIR', os.path.join(os.path.expanduser('~'), '.claude-guardrails'))
FOLDER = os.environ.get('GUARDRAILS_RELAY_DIR', os.path.join(STATE_DIR, 'relay'))
DIRECTORY = os.environ.get('GUARDRAILS_DIRECTORY_DIR', os.path.join(STATE_DIR, 'directory'))
NIGHT = os.environ.get('GUARDRAILS_NIGHT_DIR', os.path.join(STATE_DIR, 'night'))
THRESHOLD = int(os.environ.get('GUARDRAILS_RELAY_THRESHOLD', '150000'))
ROLES = tuple(r.strip() for r in os.environ.get('GUARDRAILS_RELAY_ROLES', 'game,code,workshop,sound,video').split(',') if r.strip())
FRESH_NOTE_MIN = 30


def now():
    return datetime.datetime.now().replace(microsecond=0)


def read(role):
    try:
        return json.load(open(os.path.join(FOLDER, f'{role}.json'), encoding='utf-8-sig'))
    except Exception:
        return {}


def write(role, d):
    os.makedirs(FOLDER, exist_ok=True)
    f = os.path.join(FOLDER, f'{role}.json')
    json.dump(d, open(f + '.tmp', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(f + '.tmp', f)


def card(sid):
    """This conversation's card in the session directory: its name and its size."""
    try:
        for n in os.listdir(DIRECTORY):
            if not n.endswith('.json'):
                continue
            try:
                f = json.load(open(os.path.join(DIRECTORY, n), encoding='utf-8-sig'))
            except Exception:
                continue
            if sid and f.get('sessionId') == sid:
                return f
    except Exception:
        pass
    return None


def is_night(role):
    return os.path.exists(os.path.join(NIGHT, f'running_{role}.json'))


def instruction(role, k):
    note = os.path.join(FOLDER, f'{role}.md')
    return (f"🔁 The relay: your conversation is at {k} k tokens, past the smart zone ({THRESHOLD // 1000} k). Do not cut anything: "
            f"finish what you are doing first (never in the middle of an edit, a test, or while Godot is running). "
            f"Then write your note in {note}: what is done, what is left, her decisions and her words (with the date), "
            f"the key files, what you are waiting for and from whom. Precise enough that the fresh session asks her no "
            f"question she has already settled. Then run: python -I {os.path.abspath(__file__)} --ready {role} "
            f"and stop there, without opening anything new. The dashboard will close you and reopen you, fresh, on your note.")


def post(data):
    sid = data.get('session_id', '')
    f = card(sid)
    if not f:
        return None
    role = str(data.get('role') or f.get('name') or '').lower()
    if role not in ROLES or is_night(role):
        return None
    k = int(f.get('context') or 0)
    if k < THRESHOLD:
        return None
    r = read(role)
    if r.get('session') == sid and r.get('state') in ('told', 'ready', 'running'):
        return None
    write(role, {'state': 'told', 'session': sid, 'when': now().isoformat(), 'context': k})
    return {'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': instruction(role, k // 1000)}}


def ready(role):
    role = role.lower()
    if role not in ROLES:
        return f"The relay can only reopen {', '.join(ROLES)}."
    note = os.path.join(FOLDER, f'{role}.md')
    try:
        age = (datetime.datetime.now().timestamp() - os.path.getmtime(note)) / 60
        size = os.path.getsize(note)
    except OSError:
        return f"No note: write {note} first, then run --ready {role} again."
    if age > FRESH_NOTE_MIN or size < 200:
        return f"Your note {note} is too old or too short: rewrite it (where you are, what is left, her decisions), then run --ready {role} again."
    r = read(role)
    write(role, {'state': 'ready', 'session': r.get('session', ''), 'when': now().isoformat(), 'note': note})
    return "Ready for the relay: the dashboard will close you and reopen you on your note as soon as you are idle (one minute). Stop there."


def status():
    out = []
    for r in ROLES:
        d = read(r)
        if d:
            out.append(f"{r.upper()}: {d.get('state')} ({d.get('when', '')}){' - ' + d['reason'] if d.get('reason') else ''}")
    return '\n'.join(out) or 'no relay'


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if a[:1] == ['--post']:
        try:
            r = post(json.loads(sys.stdin.read() or '{}'))
        except Exception:
            r = None      # a guard that crashes never blocks the session
        if r:
            print(json.dumps(r, ensure_ascii=False))
    elif a[:1] == ['--ready'] and len(a) > 1:
        print(ready(a[1]))
    elif a[:1] == ['--status']:
        print(status())
    else:
        print('relay.py --post | --ready <role> | --status')
