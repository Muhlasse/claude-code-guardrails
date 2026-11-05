# Tests for the relay (relay.py). Run: python -I hooks/tests/test_relay.py
import json, os, sys, tempfile, time
sys.stdout.reconfigure(encoding='utf-8')
HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='test_relay_')
for k, d in (('GUARDRAILS_RELAY_DIR', 'relay'), ('GUARDRAILS_DIRECTORY_DIR', 'directory'), ('GUARDRAILS_NIGHT_DIR', 'night')):
    os.environ[k] = os.path.join(TMP, d); os.makedirs(os.environ[k])
for k in ('GUARDRAILS_RELAY_THRESHOLD', 'GUARDRAILS_RELAY_ROLES'):
    os.environ.pop(k, None)
sys.path.insert(0, HOOKS)
import relay as R  # noqa: E402
FAILURES = []


def check(name, cond):
    print(('ok    ' if cond else 'FAIL  ') + name)
    if not cond:
        FAILURES.append(name)


def card(name, sid, ctx):
    json.dump({'pid': 1, 'name': name, 'sessionId': sid, 'context': ctx}, open(os.path.join(TMP, 'directory', f'{sid}.json'), 'w', encoding='utf-8'))


def told(r):
    return bool(r) and 'relay' in r['hookSpecificOutput']['additionalContext'].lower()


card('game', 's1', 90000)
check('under the smart zone: nothing', R.post({'session_id': 's1'}) is None)
card('game', 's1', 160000)
r = R.post({'session_id': 's1'})
check('past it: the relay instruction', told(r))
check('the instruction says finish first, then write the note', 'finish what' in r['hookSpecificOutput']['additionalContext'] and 'game.md' in r['hookSpecificOutput']['additionalContext'])
check('only once per conversation', R.post({'session_id': 's1'}) is None)
card('game', 's2', 170000)
check('a new conversation that is too long: told again', told(R.post({'session_id': 's2'})))
card('sound', 's3', 200000)
check('SOUND: the relay too', told(R.post({'session_id': 's3'})))
card('video', 's5', 200000)
check('VIDEO: the relay too', told(R.post({'session_id': 's5'})))
check('unknown session: nothing', R.post({'session_id': 'zz'}) is None)
card('code', 's4', 200000)
open(os.path.join(TMP, 'night', 'running_code.json'), 'w').write('{}')
check('at night: no relay', R.post({'session_id': 's4'}) is None)

# --ready
check('ready without a note: refused', 'No note' in R.ready('game') and R.read('game').get('state') == 'told')
open(os.path.join(TMP, 'relay', 'game.md'), 'w', encoding='utf-8').write('short')
check('note too short: refused', 'too' in R.ready('game'))
open(os.path.join(TMP, 'relay', 'game.md'), 'w', encoding='utf-8').write('- done: ...\n' * 40)
check('fresh note: ready', 'Ready' in R.ready('game') and R.read('game').get('state') == 'ready')
old = time.time() - 3600
os.utime(os.path.join(TMP, 'relay', 'game.md'), (old, old))
check('note an hour old: refused', 'too old' in R.ready('game'))
check('an unknown role: refused', 'can only reopen' in R.ready('someone'))
check('a guard that receives anything does not crash', R.post({}) is None)

print(f"\n{'ALL GREEN' if not FAILURES else str(len(FAILURES)) + ' FAILURE(S)'}")
sys.exit(1 if FAILURES else 0)
