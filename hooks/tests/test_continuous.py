# Tests for continuous mode (continuous.py). Run: python -I hooks/tests/test_continuous.py
import json, os, sys, tempfile, datetime
sys.stdout.reconfigure(encoding='utf-8')
HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='test_continuous_')
os.environ['GUARDRAILS_NIGHT_DIR'] = TMP
os.environ['GUARDRAILS_CONTINUOUS_DIR'] = os.path.join(TMP, 'continuous')
os.environ['GUARDRAILS_USAGE'] = os.path.join(TMP, 'usage.json')
os.environ['GUARDRAILS_MACHINE_NIGHT'] = os.path.join(TMP, 'machine_night.json')
for k in ('GUARDRAILS_MUST_WRITE', 'GUARDRAILS_EXEMPT_ROLES'):
    os.environ.pop(k, None)
sys.path.insert(0, HOOKS)
import continuous  # noqa: E402
FAILURES = []


def check(name, cond):
    print(('ok    ' if cond else 'FAIL  ') + name)
    if not cond:
        FAILURES.append(name)


def state(role):
    return json.load(open(os.path.join(TMP, 'continuous', f'{role}.json'), encoding='utf-8'))


def turn(role, text, quota=False):
    return continuous.decide({'role': role, 'last_assistant_message': text}, quota=quota)


# reading the line
check('continue read', continuous.read_status('blah\nSTATUS: continue — scoring the clips')[:2] == ('continue', 'scoring the clips'))
check('waiting for her choice', continuous.read_status('**STATUS: waiting for her choice — video 3**')[0] == 'user')
check('waiting for a session', continuous.read_status('STATUS: waiting for GAME — the stage')[::2] == ('session', 'GAME'))
check('nothing', continuous.read_status('Status: nothing - all done')[0] == 'nothing')
check('the last line wins', continuous.read_status('STATUS: continue — a\nSTATUS: nothing — b')[0] == 'nothing')
check('no line', continuous.read_status('just a report')[0] is None)

# VIDEO: "continue" sends it back to work
b, reason = turn('video', 'Done.\nSTATUS: continue — scoring the clips')
check('continue: blocks and sends back to work', b and 'scoring the clips' in reason)
check('state written', state('video')['state'] == 'continue')
check('above the quota: lets it stop', turn('video', 'STATUS: continue — x', quota='week')[0] is False)
check('quota noted', state('video')['state'] == 'quota')

# 40 continues in a row: pause
r = [turn('code', 'STATUS: continue — loop')[0] for _ in range(continuous.MAX_CONTINUES + 1)]
check('the first 40 relaunch', all(r[:continuous.MAX_CONTINUES]))
check('the 41st pauses', r[-1] is False and state('code')['state'] == 'pause')

# waiting: normal stop
check('waiting for her choice: lets it stop', turn('sound', 'STATUS: waiting for her choice — pad B')[0] is False)
check('state "user"', state('sound')['state'] == 'user')

# no line: one nudge for code/sound/video, then nothing; nothing for the human-facing sessions
check('video without a line: one nudge', turn('video', 'done')[0] is True)
check('video without a line, 2nd time: lets it stop', turn('video', 'done')[0] is False)
check('noted without status', state('video')['state'] == 'no_status')
check('game without a line: free, nothing blocks', turn('game', 'hello')[0] is False and state('game')['state'] == 'free')

# during /night: this guard does nothing
json.dump({'queue': 'x', 'start': datetime.datetime.now().isoformat()}, open(os.path.join(TMP, 'running_code.json'), 'w'))
check('night running: nothing', turn('code', 'STATUS: continue — x')[0] is False)

print('\n' + (f'{len(FAILURES)} failure(s)' if FAILURES else 'all pass'))
sys.exit(1 if FAILURES else 0)
