# Tests for the night guard (night.py). Run: python -I hooks/tests/test_night.py
# Replays the two holes of a real night:
#   1. the main session was waiting for a sub-agent: 3 relaunches without a ticked item stopped it for good -> must be a pause;
#   2. the code session wrote "nothing doable left" without mentioning its tasks -> the guard must send it back to work.
import json, os, sys, tempfile, datetime
sys.stdout.reconfigure(encoding='utf-8')   # the Windows console (cp1252) cannot print every character

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='test_night_')
os.environ['GUARDRAILS_STATE_DIR'] = TMP
os.environ['GUARDRAILS_NIGHT_DIR'] = TMP
os.environ['GUARDRAILS_USAGE'] = os.path.join(TMP, 'usage.json')                 # absent: no quota line
os.environ['GUARDRAILS_MACHINE_NIGHT'] = os.path.join(TMP, 'machine_night.json')  # absent: the machine was not woken
os.environ['GUARDRAILS_PRODUCTION'] = os.path.join(TMP, 'production.md')
os.environ['GUARDRAILS_TIMER_DIR'] = TMP                                         # no timer: real timers stay out of it
os.environ.pop('GUARDRAILS_AWAY', None)
os.environ.pop('GUARDRAILS_WAKE_COMMAND', None)
sys.path.insert(0, HOOKS)
import night  # noqa: E402

open(os.environ['GUARDRAILS_PRODUCTION'], 'w', encoding='utf-8').write(
    "# Production\n## S1 — grey box\n- [ ] Floor 2, the walkways (3h) [code] — note\n- [x] Already done (1h) [code]\n"
    "- [ ] Main character presentable (10h) [visual]\n## After the demo\n- [ ] A post-demo feature [code]\n")
FAILURES = []


def check(name, cond):
    print(('ok    ' if cond else 'FAIL  ') + name)
    if not cond:
        FAILURES.append(name)


def night_of(role, text):
    queue = os.path.join(TMP, f'queue_{role}.md')
    open(queue, 'w', encoding='utf-8').write(text)
    marker = os.path.join(TMP, f'running_{role}.json')
    json.dump({'queue': queue, 'start': datetime.datetime.now().isoformat()}, open(marker, 'w', encoding='utf-8'))
    return queue, marker


# 1. the main session waits for a sub-agent: pause, not stop
queue, marker = night_of('game', '- [x] done\n- [ ] harmony (waiting for the modeller)\n')
e = {'role': 'game'}
r = [night.decide(e)[0] for _ in range(4)]
check('the first relaunches send it back to work', r[:3] == [True, True, True])
check('at the 3rd without a ticked item, it may pause', r[3] is False)
check('the marker stays during the pause', os.path.exists(marker))
check('the pause does not write "stop" in the queue', 'stop' not in open(queue, encoding='utf-8').read())
open(queue, 'a', encoding='utf-8').write('- [x] harmony (the modeller delivered)\n')
check('the sub-agent delivers: the guard relaunches it', night.decide(e)[0] is True)
for _ in range(200):
    if not os.path.exists(marker):
        break
    night.decide(e)
check('never moving forward, it ends up stopping (20 pauses at most)', not os.path.exists(marker))

# 2. CODE writes "nothing doable left" without naming its tasks
queue, marker = night_of('code', '- [x] corner\n- [~] cage (waiting for her choice)\n\n## Summary\n- nothing doable left\n')
e = {'role': 'code'}
b, reason = night.decide(e)
check('Summary without its tasks: sent back to work', b is True and 'Floor 2, the walkways' in reason)
check('done tasks, other roles\' tasks and post-demo tasks are not asked for',
      'Already done' not in reason and 'Main character presentable' not in reason and 'post-demo feature' not in reason)
open(queue, 'a', encoding='utf-8').write("- Floor 2, the walkways: waiting for her choice (question walkways_difficulty)\n")
# without "Ahead" and "Further", the Summary is refused
b, reason = night.decide(e)
check('Summary without reserve: sent back to prepare ahead', b is True and 'Ahead' in reason and 'Further' in reason)
open(queue, 'a', encoding='utf-8').write("\n## Ahead\n- [x] settings A and B ready for walkways_difficulty\n")
b, reason = night.decide(e)
check('"Ahead" alone: "Further" is still missing', b is True and 'Further' in reason.split('Missing')[1].split('.')[0]
      and 'Ahead' not in reason.split('Missing')[1].split('.')[0])
open(queue, 'a', encoding='utf-8').write("\n## Further\n")
check('empty "Further" heading: refused', night.decide(e)[0] is True)
open(queue, 'a', encoding='utf-8').write("- nothing: all S2 tasks wait for approved references\n")
check('Summary naming each task, with its reserve: it may stop', night.decide(e)[0] is False and not os.path.exists(marker))

# 3. the dashboard's mailbox does not "wake" her; her own words do
check('a ✉ message from the dashboard is not her', not night.from_her({'prompt': '✉ from VIDEO (via the dashboard): video ready'}))
check('a ✉ "she answered" message is not her', not night.from_her({'prompt': '✉ from DASHBOARD (via the dashboard): she answered your question'}))
check('her words typed on the dashboard are her', night.from_her({'prompt': '(my answer to your question, from the dashboard) A'}))

# 4. what worked must still work
queue, marker = night_of('game', "- [x] a\n- [~] b\n\n## Ahead\n- [x] c\n\n## Further\n- [x] d\n\n"
                                  "## Summary\n- Main character presentable: waiting for her choice\n")
# the main session that names its tasks no longer stops: it explores like away mode
b, reason = night.decide({'role': 'game'})
check('main session naming its tasks: the night goes on exploring', b is True and 'like away mode' in reason and '--since' in reason)
check('exploration is recorded in the marker', json.load(open(marker, encoding='utf-8')).get('explore') is True)
check('exploration asks no question on the dashboard', 'no questions on the dashboard' in reason)
night.above_line, _real = (lambda *a: 'week at 80 % for a line at 60 %'), night.above_line
b, reason = night.decide({'role': 'game'})
check('exploration above the quota line: pause', b is True and 'quota line' in reason)
night.above_line = _real
t = json.load(open(marker, encoding='utf-8')); t['paused'] = False; json.dump(t, open(marker, 'w', encoding='utf-8'))
open(queue, 'a', encoding='utf-8').write("\n## Exploration\n- [ ] the door: 3 attempts\n")
b, reason = night.decide({'role': 'game'})
check('exploration with an open item: away-mode instruction, no question', b is True and 'Exploring night' in reason and '-Wait' not in reason)
open(queue, 'w', encoding='utf-8').write(open(queue, encoding='utf-8').read().replace('- [ ] the door', '- [x] the door'))
b, reason = night.decide({'role': 'game'})
check('exploration, empty queue without its summary: the next decision', b is True and 'like away mode' in reason)
open(queue, 'a', encoding='utf-8').write("\n## Summary of the exploration\n- the door: 3 attempts in report.json\n")
# the Summary of the exploration no longer stops: the night moves on to another decision
b, reason = night.decide({'role': 'game'})
check('"Summary of the exploration" written, empty queue: the night moves on to another decision', b is True and os.path.exists(marker) and 'another' in reason)
os.remove(marker)
queue, marker = night_of('code', "- [x] a\n- [~] b\n\n## Ahead\n- [x] c\n\n## Further\n- [x] d\n\n"
                                  "## Summary\n- Floor 2, the walkways: waiting for GAME\n- A post-demo feature: on hold\n")
check('CODE naming its tasks: stop accepted (no exploration)', night.decide({'role': 'code'})[0] is False and not os.path.exists(marker))
queue, marker = night_of('game', '- [x] a\n')
b, reason = night.decide({'role': 'game'})
check('empty queue without Summary: the next task is asked for', b is True and 'production.md' in reason)
os.remove(marker)
check('without a marker, the guard does nothing', night.decide({'role': 'game'})[0] is False)

# 5. her bedtime "ok": not a wake-up during the first 20 minutes
queue, marker = night_of('game', '- [ ] a\n')
check('"ok" right after /night: not a wake-up', night.wake({'role': 'game', 'prompt': 'ok'}) == '' and os.path.exists(marker))
check('a ✉ message from CODE: not a wake-up', night.wake({'role': 'game', 'prompt': '✉ from CODE (via the dashboard): night received'}) == '')
json.dump({'queue': queue, 'start': (datetime.datetime.now() - datetime.timedelta(hours=2)).isoformat()}, open(marker, 'w', encoding='utf-8'))
check('two hours later, her message wakes it', night.wake({'role': 'game', 'prompt': 'hi'}) != '' and not os.path.exists(marker))

# 6. away mode: the dashboard button decides, not the hour nor the tasks
AWAY = os.path.join(TMP, 'away.json')
night.AWAY = AWAY


def away(text, minutes_ago=30):
    start = (datetime.datetime.now() - datetime.timedelta(minutes=minutes_ago)).isoformat(timespec='seconds')
    json.dump({'active': True, 'start': start}, open(AWAY, 'w', encoding='utf-8'))
    queue, marker = night_of('game', text)
    json.dump({'queue': queue, 'start': start, 'mode': 'away'}, open(marker, 'w', encoding='utf-8'))
    return queue, marker


queue, marker = away('- [ ] variants of the bedroom door\n')
b, reason = night.decide({'role': 'game'})
check('away, queue not empty: back to work, everything in report.json', b is True and 'Away mode' in reason and 'report.json' in reason)
queue, marker = away('- [x] variants of the bedroom door\n')
b, reason = night.decide({'role': 'game'})
check('away, empty queue: restart from where the game is (context command), try bold', b is True and night.AWAY_CONTEXT_CMD in reason and 'bold' in reason)
queue, marker = away('- [x] a\n\n## Summary\n- 2 proposals on the dashboard\n')
check('away, Summary written: stop without asking for "Ahead" or its tasks', night.decide({'role': 'game'})[0] is False and not os.path.exists(marker))
queue, marker = away('- [ ] a\n')
json.dump({'active': False, 'start': '2026-01-01T00:00:00', 'end': datetime.datetime.now().isoformat(timespec='seconds')}, open(AWAY, 'w', encoding='utf-8'))
check('"I\'m back" on the dashboard: stop', night.decide({'role': 'game'})[0] is False and not os.path.exists(marker)
      and 'back' in open(queue, encoding='utf-8').read())
queue, marker = away('- [ ] a\n')
json.dump({'active': False, 'start': '2026-01-01T00:00:00', 'end': '2026-01-01T01:00:00'}, open(AWAY, 'w', encoding='utf-8'))
check('an old finished absence does not cut the new one', night.decide({'role': 'game'})[0] is True)
queue, marker = away('- [ ] a\n', minutes_ago=2)
check('away: "ok" right after the click is not a return', night.wake({'role': 'game', 'prompt': 'ok'}) == '' and os.path.exists(marker))
queue, marker = away('- [ ] a\n', minutes_ago=10)
r = night.wake({'role': 'game', 'prompt': 'hi, I am here'})
check('away: her message after 5 min = her return, the dashboard goes back to normal',
      'back' in r and not os.path.exists(marker) and json.load(open(AWAY, encoding='utf-8'))['active'] is False)
queue, marker = night_of('game', '- [ ] a\n')
json.dump({'active': False, 'end': datetime.datetime.now().isoformat()}, open(AWAY, 'w', encoding='utf-8'))
check('a real night does not stop on the away button', night.decide({'role': 'game'})[0] is True)
os.remove(marker)

print(f"\n{'ALL GREEN' if not FAILURES else str(len(FAILURES)) + ' FAILURE(S)'}")
sys.exit(1 if FAILURES else 0)
