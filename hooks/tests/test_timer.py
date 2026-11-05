# Tests for the universal timer (timer.py). Run: python -I hooks/tests/test_timer.py
import json, os, sys, tempfile, datetime
sys.stdout.reconfigure(encoding='utf-8')
HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='test_timer_')
os.environ['GUARDRAILS_STATE_DIR'] = TMP
os.environ['GUARDRAILS_TIMER_DIR'] = TMP
os.environ['GUARDRAILS_REFUSALS'] = os.path.join(TMP, 'refusals.jsonl')
os.environ['GUARDRAILS_NIGHT_DIR'] = TMP
os.environ['GUARDRAILS_USAGE'] = os.path.join(TMP, 'usage.json')
os.environ['GUARDRAILS_MACHINE_NIGHT'] = os.path.join(TMP, 'machine_night.json')
os.environ['GUARDRAILS_AWAY'] = os.path.join(TMP, 'away.json')
for k in ('GUARDRAILS_ROLES', 'GUARDRAILS_TIMER_ALLOWED'):
    os.environ.pop(k, None)
sys.path.insert(0, HOOKS)
import timer as M  # noqa: E402
FAILURES = []
GAME_FILE = 'C:/project/game/scenes/a.gd'


def check(name, cond):
    print(('ok    ' if cond else 'FAIL  ') + name)
    if not cond:
        FAILURES.append(name)


def tool(name, **ti):
    return {'role': 'game', 'tool_name': name, 'tool_input': ti}


def denied(e):
    r = M.pre(e)
    return bool(r) and r['hookSpecificOutput']['permissionDecision'] == 'deny'


check('no timer: nothing is blocked', not denied(tool('Edit', file_path=GAME_FILE)))
check('start a timer', 'started' in M.start('game', 90, 'the door'))
check('a 2nd timer during the 1st: refused', 'Refused' in M.start('game', 30, 'something else'))
check('during the time: the game can be edited', not denied(tool('Edit', file_path=GAME_FILE)))
check('during the time: nothing to say after a tool', M.post(tool('Read')) is None)

m = M.read('game'); m['end'] = (M.now() + datetime.timedelta(minutes=10)).isoformat(); M.write(m)
r = M.post(tool('Read'))
check('last quarter of an hour: warned once', r and 'Only' in r['hookSpecificOutput']['additionalContext'] and M.post(tool('Read')) is None)

m = M.read('game'); m['end'] = (M.now() - datetime.timedelta(minutes=1)).isoformat(); M.write(m)
check('time up: editing the game is denied', denied(tool('Edit', file_path=GAME_FILE)))
check('time up: Blender denied', denied(tool('mcp__blender2__execute_blender_code', code='x')))
check('time up: launching Godot denied', denied(tool('PowerShell', command='& godot --headless')))
check('time up: a new sub-agent denied', denied(tool('Agent', prompt='continue')))
check('time up: reading passes', not denied(tool('Read', file_path='x')))
check('time up: the JOURNAL passes', not denied(tool('Edit', file_path='C:\\project\\JOURNAL.md')))
check('time up: the night queue and report.json pass', not denied(tool('Write', file_path=os.path.join(TMP, 'away', 'x', 'report.json'))))
check('time up: asking her the question passes', not denied(tool('AskUserQuestion')))
check('time up: the /end commit passes', not denied(tool('PowerShell', command='tools\\commit.ps1 "x"')))
r = M.post(tool('Read'))
check('time up: the session is told', r and 'TIME UP' in r['hookSpecificOutput']['additionalContext'])
check('time up: restarting a timer is refused', 'Refused' in M.start('game', 60, 'the door, again'))
check('another session is not affected', not denied({'role': 'code', 'tool_name': 'Edit', 'tool_input': {'file_path': 'C:/project/game/a.gd'}}))
check('release the timer', 'released' in M.done('game') and not denied(tool('Edit', file_path='C:/project/game/a.gd')))
m = M.read('game'); m.update(state='stopped', end=(M.now() + datetime.timedelta(minutes=50)).isoformat()); M.write(m)
check('she clicked "stop": blocked even before the hour', denied(tool('Edit', file_path='C:/project/game/a.gd')))

# at night there is no timer: only her "stop" still blocks
_before = M.read('game')
M.write({'role': 'game', 'work': 'the night', 'start': '2026-01-01T00:00:00', 'minutes': 30, 'end': '2026-01-01T00:30:00', 'state': 'running', 'said': []})
_marker = os.path.join(TMP, 'running_game.json')
check('no night, time up: Edit denied', denied(tool('Edit', file_path=GAME_FILE)))
json.dump({'queue': 'x.md', 'start': '2026-01-01T00:00:00'}, open(_marker, 'w', encoding='utf-8'))
check('at night, time up: Edit accepted', not denied(tool('Edit', file_path=GAME_FILE)))
check('at night, time up: no reminder', M.post(tool('Edit', file_path=GAME_FILE)) is None)
_m = M.read('game'); _m['state'] = 'stopped'; M.write(_m)
check('at night, her "stop": Edit denied', denied(tool('Edit', file_path=GAME_FILE)))
_m['state'] = 'running'; M.write(_m)
json.dump({'queue': 'x.md', 'start': '2026-01-01T00:00:00', 'mode': 'away'}, open(_marker, 'w', encoding='utf-8'))
check('away, time up: Edit denied (away mode keeps its time)', denied(tool('Edit', file_path=GAME_FILE)))
os.remove(_marker)
if _before: M.write(_before)
else: os.remove(os.path.join(TMP, 'game.json'))

# away mode stops at the timer
import night  # noqa: E402
start = (datetime.datetime.now() - datetime.timedelta(minutes=95)).isoformat(timespec='seconds')
json.dump({'active': True, 'start': start}, open(os.environ['GUARDRAILS_AWAY'], 'w', encoding='utf-8'))
queue = os.path.join(TMP, 'queue_game.md'); open(queue, 'w', encoding='utf-8').write('- [ ] door, attempt B\n')
marker = os.path.join(TMP, 'running_game.json')
json.dump({'queue': queue, 'start': start, 'mode': 'away'}, open(marker, 'w', encoding='utf-8'))
b, reason = night.decide({'role': 'game'})
check('away, time up: it writes its Summary', b is True and 'Summary' in reason and 'report.json' in reason)
open(queue, 'a', encoding='utf-8').write('\n## Summary\n- the door: 2 attempts\n')
check('away, time up, Summary written: stop', night.decide({'role': 'game'})[0] is False and not os.path.exists(marker))

try:
    _refusals = [json.loads(l) for l in open(os.environ['GUARDRAILS_REFUSALS'], encoding='utf-8')]
except OSError:
    _refusals = []
check('every timer refusal is logged for the dashboard', bool(_refusals) and all(r.get('guard') == 'timer' for r in _refusals))
print(f"\n{'ALL GREEN' if not FAILURES else str(len(FAILURES)) + ' FAILURE(S)'}")
sys.exit(1 if FAILURES else 0)
