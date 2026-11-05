# The night guard (Stop hook): keeps an unattended session working through its queue while the human sleeps.
# A Claude Code session stops at the end of every reply. During /night, this guard sends it back to work until SHE
# wakes up (her rule: "night is when I sleep, not when the sun sets"): no fixed hour.
# It does nothing without the marker written by /night after her "ok":
#   <NIGHT_DIR>/running_<role>.json   {"queue": "<path of the queue file>", "start": "<iso>"}
# - wake-up: her first message to the session (UserPromptSubmit hook: night.py --wake), or the machine switched back to
#   day mode after the start (MACHINE_NIGHT file inactive);
# - queue not empty: next item; queue empty: the next open task of the role in the production plan;
# - THE LINE (quota pacing): weekly usage may rise in a straight line from 0 % at the start of the week to 100 % at the
#   reset. Above it (or the 5-hour window nearly full): pause; `night.py --wait` in the background waits until the line
#   catches up, then the session resumes;
# - stop: her wake-up, 16 h at most, 200 relaunches, or a Summary written because nothing doable is left;
# - 3 relaunches without a ticked item (often: waiting for a background sub-agent) = PAUSE, not stop (a real night lost
#   11 h that way): the marker stays, the session resumes at its next end of reply; 20 pauses at most;
# - a "nothing doable left" Summary is accepted only if every open task of the role (production plan, sections S0 to S4)
#   is named in it with its reason (a session once stopped on its own word), and only after the sections "## Ahead"
#   (prepare every answer to the pending questions, 5 seeds, research) and "## Further" (later tasks allowed without
#   her) exist (a night once stopped at 22:30 with everything waiting for her choices: 8 h lost).
# An item waiting for her choice, or blocked, is written "- [~]" and no longer counts.
# THE EXPLORING NIGHT: when the main role has nothing doable left without her (Summary accepted), the night does not
# stop: it goes on like away mode, one upcoming decision at a time, 2-3 real attempts, everything in report.json for the
# dashboard's away page. End: her wake-up, the quota line (pause), 16 h, 200 relaunches. A "## Summary of the exploration"
# no longer stops it (one decision done -> another one that does not depend on her).
# The code role keeps the old stop (its work is measurements, not attempts to look at).
# AWAY MODE: `/night away`, started from the dashboard's "I'm away" button, while she does something else. The marker
# carries "mode": "away". The main role starts from where the game is (AWAY_CONTEXT_CMD), tries truly different
# directions, and writes EVERYTHING to report.json (AWAY_FOLDER_CMD) for the away page; no question on the dashboard
# while she is away. End: the "I'm back" button (AWAY file inactive) or her message (5 min of grace, not 20).
import json, os, re, sys, time, datetime

STATE_DIR = os.environ.get('GUARDRAILS_STATE_DIR', os.path.join(os.path.expanduser('~'), '.claude-guardrails'))
NIGHT = os.environ.get('GUARDRAILS_NIGHT_DIR', os.path.join(STATE_DIR, 'night'))
USAGE = os.environ.get('GUARDRAILS_USAGE', os.path.join(STATE_DIR, 'usage.json'))            # written by the status line
MACHINE_NIGHT = os.environ.get('GUARDRAILS_MACHINE_NIGHT', os.path.join(STATE_DIR, 'machine_night.json'))
AWAY = os.environ.get('GUARDRAILS_AWAY', os.path.join(NIGHT, 'away.json'))                   # the dashboard button
PROD = os.environ.get('GUARDRAILS_PRODUCTION',
                      os.path.join(os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd()), 'docs', 'production.md'))
TAGS = {'code': ('[code]',), 'game': ('[visual]', '[text]')}   # which production tasks belong to which role
EXPLORE_ROLES = ('game',)            # roles whose night goes on exploring instead of stopping
HUMAN_FACING = ('game', 'workshop')  # she only talks to these sessions
SESSIONS = os.path.join(os.path.expanduser('~'), '.claude', 'sessions')
PYTHON = os.environ.get('GUARDRAILS_PYTHON', sys.executable or 'python')
WAKE_COMMAND = os.environ.get('GUARDRAILS_WAKE_COMMAND', '')   # optional: puts the machine back in day mode
AWAY_CONTEXT_CMD = os.environ.get('GUARDRAILS_AWAY_CONTEXT', 'python -I tools/away.py --context')
AWAY_FOLDER_CMD = os.environ.get('GUARDRAILS_AWAY_FOLDER', 'python -I tools/away.py --folder')
REPORT = 'report.json'
FIVE_H_MAX = 95


def role_from_session(sid):
    try:
        for n in os.listdir(SESSIONS):
            if not n.endswith('.json'):
                continue
            try:
                s = json.load(open(os.path.join(SESSIONS, n), encoding='utf-8'))
            except Exception:
                continue
            if s.get('sessionId') == sid:
                return str(s.get('name') or '').lower()
    except Exception:
        pass
    return ''


def role_from_process():
    """Plan B (a session started by conhost did not write its session file): walk up the parents of this hook to the
    claude.exe that started it and read its "-n <role>". Windows only."""
    if os.name != 'nt':
        return ''
    import subprocess
    ps = (f"$id={os.getpid()}; for($i=0;$i -lt 10;$i++){{ $p=Get-CimInstance Win32_Process -Filter \"ProcessId=$id\"; "
          "if(-not $p){break}; if($p.Name -eq 'claude.exe'){ $p.CommandLine; break }; $id=$p.ParentProcessId }")
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=20,
                             creationflags=0x08000000).stdout
    except Exception:
        return ''
    m = re.search(r'(?:^|\s)-n\s+"?(\w+)', out or '')
    return m.group(1).lower() if m else ''


def read_marker(f):
    """The marker, even hand-written with single backslashes in a Windows path (invalid JSON = silent guard).
    Without a readable "start", the file's modification time is used."""
    txt = open(f, encoding='utf-8-sig').read()
    try:
        t = json.loads(txt)
    except Exception:
        t = json.loads(txt.replace('\\', '\\\\'))   # Windows path typed as is: double every backslash
    try:
        datetime.datetime.fromisoformat(str(t.get('start', ''))).replace(tzinfo=None)
    except Exception:
        t['start'] = datetime.datetime.fromtimestamp(os.path.getmtime(f)).isoformat(timespec='seconds')
    return t


def find_role(data):
    role = data.get('role') or role_from_session(data.get('session_id', ''))
    if role:
        return role
    # plan B costs a second: only if a night is running
    try:
        if not any(n.startswith('running_') for n in os.listdir(NIGHT)):
            return ''
    except Exception:
        return ''
    return role_from_process()


def note(queue, line):
    try:
        with open(queue, 'a', encoding='utf-8') as f:
            f.write('\n' + line + '\n')
    except Exception:
        pass


def open_tasks(role):
    """Short names of the role's "- [ ]" tasks in the production plan, sections S0 to S4 (not post-demo sections)."""
    tags = TAGS.get(role)
    if not tags:
        return []
    try:
        lines = open(PROD, encoding='utf-8-sig').read().splitlines()
    except Exception:
        return []
    names, inside = [], False
    for l in lines:
        if l.startswith('## '):
            inside = bool(re.match(r'## S\d', l))
            continue
        if inside and re.match(r'^\s*- \[ \]', l) and any(t in l for t in tags):
            title = re.sub(r'^\s*- \[ \]\s*', '', l).replace('*', '')
            title = re.split(r'\s\(|\s—\s|\s\[', title)[0].strip()
            if title:
                names.append(title)
    return names


def forgotten_tasks(role, text):
    """The role's tasks that the night queue does not name (it must say why each one needs her)."""
    low = text.lower()
    return [n for n in open_tasks(role) if n.lower()[:30] not in low]


RESERVE = (('Ahead', r'Ahead'), ('Further', r'Further'))


def missing_sections(text):
    """The reserve sections that are absent (or have no "- " line under them)."""
    missing = []
    for name, pattern in RESERVE:
        m = re.search(r'^#+\s*' + pattern + r'.*$((?:\n(?!#).*)*)', text, re.M | re.I)
        if not m or not re.search(r'^\s*- ', m.group(1), re.M):
            missing.append(f'"## {name}"')
    return missing


def the_line(now_ts=None):
    """(real weekly usage, line, 5-hour window) in %, or None if usage is unknown."""
    try:
        u = json.load(open(USAGE, encoding='utf-8-sig'))['limits']
        s = u['seven_day']; reset = float(s['resets_at'])
    except Exception:
        return None
    now = now_ts or time.time()
    start = reset - 7 * 86400
    line = 100 * max(0.0, min(1.0, (now - start) / (reset - start)))
    five = u.get('five_hour') or {}
    c = float(five.get('used_percentage') or 0)
    if five.get('resets_at') and now >= float(five['resets_at']):
        c = 0.0   # the 5-hour window has already restarted
    return float(s.get('used_percentage') or 0), round(line, 1), c


def above_line(now_ts=None):
    q = the_line(now_ts)
    if not q:
        return None
    real, line, five = q
    if real > line:
        return f'week at {real:.0f} % for a line at {line:.0f} %'
    if five >= FIVE_H_MAX:
        return f'5-hour window at {five:.0f} %'
    return None


def machine_awake(start):
    """The machine was switched back to day mode after the night started."""
    try:
        d = json.load(open(MACHINE_NIGHT, encoding='utf-8-sig'))
        when = datetime.datetime.fromtimestamp(os.path.getmtime(MACHINE_NIGHT))
    except Exception:
        return False
    return (not d.get('active')) and when > start


def is_back(start):
    """Away mode: she clicked "I'm back" after the start (or the dashboard's file is gone)."""
    try:
        d = json.load(open(AWAY, encoding='utf-8-sig'))
    except Exception:
        return True
    if d.get('active'):
        return False
    try:
        return datetime.datetime.fromisoformat(str(d.get('end') or '')).replace(tzinfo=None) >= start.replace(tzinfo=None)
    except Exception:
        return True


def time_up(role):
    """The role's timer is up (hooks/timer.py)."""
    try:
        import timer
        return timer.expired(timer.read(role))
    except Exception:
        return False


def end_away():
    try:
        d = json.load(open(AWAY, encoding='utf-8-sig'))
        if d.get('active'):
            d['active'] = False; d['end'] = datetime.datetime.now().isoformat(timespec='seconds')
            json.dump(d, open(AWAY, 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception:
        pass


def explore(t, queue):
    """The exploring night's instruction: the same as away mode, filed in a "_night" folder."""
    folder = f"{AWAY_FOLDER_CMD} --since {t.get('start', '')}"
    return ("Night mode, continuing like away mode (the night no longer stops for lack of work). She is asleep: "
            f"no questions on the dashboard. Run {AWAY_CONTEXT_CMD} again (the game may have changed) and take the next decision "
            "she will face in the current work (or the next one in the demo's story); never a refused direction, never a question "
            f"already asked that is waiting for her answer. Add it to {queue} under \"## Exploration\" as \"- [ ]\" items. Her rule "
            "\"less, but better\": 1 h 30 to 2 h per decision. First ALL her verdicts on the subject, the scoring grid "
            "and the research on how professionals solved it. Then 2 or 3 real attempts in the real scene (one of them bold), apart from "
            "the approved game (an --option=, never the default). Each one goes through at least 3 rounds (played, captured, reviewed "
            f"against her verdicts, fixed). EVERYTHING goes into {REPORT} ({folder}): a full-frame view from the same spot as "
            "\"before\", her own words, the rounds, and \"play\" (the scene and its options). One decision done: move to another "
            "one that does not depend on her (the next place, another part of the demo). No Summary stops the night: only her "
            "wake-up, the quota and the relaunch limit stop it. Truly nothing here: write why under "
            "\"## Summary of the exploration\" and take another part of the demo.")


def decide(data, now=None):
    """Stop hook. Returns (block, reason). Separate from main() for the tests."""
    now = now or datetime.datetime.now()
    role = find_role(data)
    if not role:
        return False, ''
    marker = os.path.join(NIGHT, f'running_{role}.json')
    if not os.path.exists(marker):
        return False, ''
    try:
        t = read_marker(marker)
    except Exception:
        return False, ''
    queue = t.get('queue', '')

    def stop(why):
        if os.path.exists(marker):
            os.remove(marker)
        note(queue, f'_(night guard: stop, {why}, {now:%H:%M})_')
        return False, ''

    def keep(reason):
        json.dump(t, open(marker, 'w', encoding='utf-8'), ensure_ascii=False)
        return True, reason

    try:
        start = datetime.datetime.fromisoformat(t.get('start', ''))
    except Exception:
        start = now
    if now - start > datetime.timedelta(hours=16):
        return stop('16 h passed')
    away = t.get('mode') == 'away'
    if away and is_back(start):
        return stop('she is back (dashboard button)')
    if not away and machine_awake(start):
        return stop('she is awake (machine back in day mode)')
    try:
        text = open(queue, encoding='utf-8-sig').read()
    except Exception:
        return stop('queue file not found')
    has_summary = bool(re.search(r'^#+\s*Summary', text, re.M | re.I))
    summary_explo = bool(re.search(r"^#+\s*Summary of the exploration", text, re.M | re.I))  # noqa: F841 (kept for reading)
    empty = len(re.findall(r'^\s*- \[ \]', text, re.M))
    done = len(re.findall(r'^\s*- \[[xX]\]', text, re.M))
    relaunches = int(t.get('relaunches', 0))
    if relaunches >= 200:
        return stop('200 relaunches')
    if away and has_summary and empty == 0:
        return stop('nothing left to explore, Summary written')
    if away and time_up(role):
        # the timer: when the time is up, the Summary, then stop
        if has_summary:
            return stop('time up (timer), Summary written')
        if int(t.get('summary_asked', 0)) >= 3:
            return stop('time up (timer)')
        t['summary_asked'] = int(t.get('summary_asked', 0)) + 1
        return keep("⏱ Away mode: the time chosen with her is up (dashboard timer). We stop without extending. "
                    f"Write \"end\" and \"summary\" in {REPORT} ({AWAY_FOLDER_CMD}): what is done and what is left. Also write the "
                    f"\"## Summary\" of {queue}, then stop. Do not open anything new.")
    exploring = bool(t.get('explore')) and not away
    # the "Summary of the exploration" no longer stops the night (one decision done -> another);
    # only her wake-up, the quota (pause) and the 200 relaunches stop it.
    if has_summary and empty == 0 and not exploring:
        forgotten = forgotten_tasks(role, text)
        missing = missing_sections(text)
        if not forgotten and missing and t.get('reserve_refused', 0) < 3:
            t['reserve_refused'] = int(t.get('reserve_refused', 0)) + 1; t['relaunches'] = relaunches + 1
            return keep(
                "Night mode: no Summary yet. Queue empty: the night goes on in two steps. "
                "1) \"## Ahead\": for every question waiting for her choice, prepare every answer (the settings of A, B, "
                "C ready as attempts, without touching the approved game) so her choice applies as soon as she wakes up; redo the "
                "measurements with 5 seeds instead of one; research how professionals did the next 2 tasks of your role. "
                "2) \"## Further\": the next tasks of your role (S2-S3), only what the rules allow without her "
                "(proposals ready for the dashboard, grey blocks, kit, tests); never final art without an approved reference, never "
                f"a refused direction. Missing: {', '.join(missing)}. Write these sections in {queue} with \"- [ ]\" items and "
                "start the first one. Nothing doable in a section: one line \"- nothing: <why>\" under it.")
        if not forgotten or t.get('summary_refused', 0) >= 3:
            if role in EXPLORE_ROLES:
                # the night no longer stops for lack of work: it explores like away mode
                t['explore'] = True; t['relaunches'] = relaunches + 1
                note(queue, f'_(night guard: nothing doable left without her; the night goes on exploring, like away mode, {now:%H:%M})_')
                return keep(explore(t, queue))
            return stop('nothing doable left without her, Summary written')
        t['summary_refused'] = int(t.get('summary_refused', 0)) + 1; t['relaunches'] = relaunches + 1
        return keep(f"Night mode: your Summary says \"nothing doable left without her\", but these tasks of your role in "
                    f"{os.path.basename(PROD)} are not in it: " + " ; ".join(forgotten[:8]) + ". For each one: either turn it into 1 to 3 "
                    f"\"- [ ]\" items in {queue} and start, or write in the Summary its name and why it needs her "
                    "(waiting for her choice: which question; or after which task). Never a direction she refused.")

    # the quota line: on pause, the session stops; "night.py --wait" (background) will wake it up
    too_much = above_line()
    if t.get('paused'):
        if too_much:
            return False, ''          # it is waiting, nothing to do
        t['paused'] = False           # the line caught up: carry on below
    elif too_much:
        t['paused'] = True
        return keep(f"Night mode: above the quota line ({too_much}). She does not want it crossed. "
                    f"Start in the background (run_in_background): \"{PYTHON}\" \"{os.path.abspath(__file__)}\" --wait "
                    "then end your reply without doing anything else. You will be woken up when the line has caught up with you.")

    if empty == 0 and away:
        t['done_seen'] = done; t['relaunches'] = relaunches + 1
        return keep(f"Away mode: your queue is empty and she is not back yet. Run {AWAY_CONTEXT_CMD} again (the game may have changed), "
                    "take the next decision she will face in the current work (or the next one in the demo's story), "
                    f"and add it to {queue} as \"- [ ]\" items. Her rule \"less, but better\": 1 h 30 to 2 h for this decision. "
                    "First ALL her verdicts on the subject, the scoring grid and thorough research on how professionals solved it. "
                    "Then 2 or 3 real attempts in the real scene (one of them bold), apart from the approved game. Each one goes through "
                    "at least 3 rounds (played, captured, reviewed against her verdicts, fixed). EVERYTHING goes into "
                    f"{REPORT} ({AWAY_FOLDER_CMD}): a full-frame view from the same spot as \"before\", her own words, the rounds. "
                    "No questions on the dashboard. Nothing left to explore: write the \"## Summary\" and stop.")
    if empty == 0 and exploring:
        t['done_seen'] = done; t['relaunches'] = relaunches + 1
        return keep(explore(t, queue))
    if empty == 0:
        t['done_seen'] = done; t['relaunches'] = relaunches + 1
        return keep(f"Night mode: your queue is empty, and she wants the night to be useful until she wakes up. "
                    f"Add to {queue} the next task of your role from {os.path.basename(PROD)}, split into 1 to 3 \"- [ ]\" items "
                    "that do not need her (never a direction she refused, never what waits for her choice), then do the first one. "
                    "Nothing doable left without her: write the \"## Summary\" and stop.")

    if done == t.get('done_seen', -1):
        t['no_progress'] = int(t.get('no_progress', 0)) + 1
    else:
        t['no_progress'] = 0
    if t['no_progress'] >= 3:
        # pause, not stop: often it waits for a background sub-agent; it resumes at its next end of reply
        t['pauses'] = int(t.get('pauses', 0)) + 1
        if t['pauses'] > 20:
            return stop('20 pauses without progress')
        t['no_progress'] = 0
        json.dump(t, open(marker, 'w', encoding='utf-8'), ensure_ascii=False)
        return False, ''
    t['done_seen'] = done; t['relaunches'] = relaunches + 1
    if away or exploring:
        folder = f"{AWAY_FOLDER_CMD} --since {t.get('start', '')}" if exploring else AWAY_FOLDER_CMD
        return keep(f"{'Exploring night' if exploring else 'Away mode'}: {empty} \"- [ ]\" item(s) left in {queue}. "
                    f"She is {'asleep' if exploring else 'doing something else'}: do not ask her anything, "
                    f"she will see everything on the away page. Update {REPORT} at every round: a full-frame view from the "
                    f"same spot as \"before\", \"what changes\" in her words, the rounds; discarded ones included ({folder}). "
                    "No questions on the dashboard. No quick sloppy attempt: dig into the current one (at least 3 rounds) before "
                    "opening another. Take the next one, do it, tick it with its proof. Waiting for a background sub-agent? Start "
                    "the next one meanwhile. Blocked after two tries: \"- [~]\" with the reason.")
    return keep(f"Night mode (/night): {empty} \"- [ ]\" item(s) left in {queue}. She is asleep: do not ask her anything. "
                "Take the next one, do it, tick it with its proof. Waiting for a background sub-agent? "
                "Start the next one meanwhile (or add the next task of your role). An item that needs her choice: ask on the "
                "dashboard without -Wait, then write \"- [~]\" in its place. Blocked after two tries: \"- [~]\" with the reason.")


# What arrives as a "message" without coming from her (a sub-agent's report once passed for her wake-up and stopped the
# night after half an hour).
NOT_HER = ('<cross-session-message', '<agent-message', '[Subagent hand-back]', '<task-notification',
           'Another Claude session sent a message', 'This session is being continued', '<command-name>/night',
           '✉ from ')   # the dashboard's mailbox: a message from another session, not her


BEDTIME_S = 20 * 60   # time to go to bed: her messages are not yet a wake-up
LEAVING_S = 5 * 60    # away mode: time to leave (an "ok" right after the click is not a return)


def from_her(data):
    p = str(data.get('prompt') or '').lstrip()
    if not p:
        return False
    return not any(m in p[:2000] for m in NOT_HER)


def wake(data):
    """UserPromptSubmit hook: a message from her during the night = she is awake. Returns the text added to the context."""
    if not from_her(data):
        return ''   # a message from another session, a sub-agent or a background task: she is still asleep
    role = find_role(data)
    if role not in HUMAN_FACING:
        return ''   # she only talks to the human-facing sessions; a message between sessions wakes nothing
    marker = os.path.join(NIGHT, f'running_{role}.json')
    if not marker or not os.path.exists(marker):
        return ''
    try:
        t = read_marker(marker)
    except Exception:
        t = {}
    # her bedtime "ok", 1 min 30 after /night, was once taken for her wake-up. During the first 20 minutes of the
    # night she is still going to bed: her messages wake nothing.
    try:
        grace = LEAVING_S if t.get('mode') == 'away' else BEDTIME_S
        if (datetime.datetime.now() - datetime.datetime.fromisoformat(t.get('start', '')).replace(tzinfo=None)).total_seconds() < grace:
            return ''
    except Exception:
        pass
    os.remove(marker)
    queue = t.get('queue', '')
    if t.get('mode') == 'away':
        end_away()   # the dashboard goes back to normal
        note(queue, f'_(night guard: she is back, {datetime.datetime.now():%H:%M})_')
        return (f"She is back: away mode is over. If not done yet, write the Summary at the end of {queue} "
                "(5 lines at most: what you explored, your proposals on the dashboard, what is blocked and why), "
                "tell her first in two lines, then answer her message.")
    note(queue, f'_(night guard: she is awake, {datetime.datetime.now():%H:%M})_')
    if role == HUMAN_FACING[0] and WAKE_COMMAND:   # optional: the machine goes back to day mode
        try:
            if json.load(open(MACHINE_NIGHT, encoding='utf-8-sig')).get('active'):
                import subprocess
                subprocess.Popen(WAKE_COMMAND, shell=True, creationflags=0x08000000 if os.name == 'nt' else 0)
        except Exception:
            pass
    return (f"She just woke up: the night is over. If not done yet, write the Summary at the end of {queue} "
            "(5 lines at most: done, waiting for her choice, blocked and why), tell her first, then answer her message.")


def wait(max_h=10.0):
    """Run in the background during a pause: returns when the line has caught up with usage."""
    t0 = time.time()
    while time.time() - t0 < max_h * 3600:
        if not above_line():
            q = the_line()
            print(f"The line caught up with you ({q[0]:.0f} % for {q[1]:.0f} %): resume the night's work." if q else 'Usage unknown: resume.')
            return
        time.sleep(120)
    print('Still above the line after many hours: write the Summary and stop.')


if __name__ == '__main__':
    if '--wait' in sys.argv:
        wait(); sys.exit(0)
    try:
        data = json.loads(sys.stdin.buffer.read().decode('utf-8', 'replace') or '{}')   # UTF-8: otherwise non-ASCII arrives garbled (cp1252)
    except Exception:
        sys.exit(0)
    if '--wake' in sys.argv:
        try:
            text = wake(data)
        except Exception:
            text = ''
        if text:
            print(text)
        sys.exit(0)
    try:
        block, reason = decide(data)
    except Exception:
        sys.exit(0)   # a guard error must never jam a session
    if block:
        print(json.dumps({'decision': 'block', 'reason': reason}, ensure_ascii=True))
    sys.exit(0)
