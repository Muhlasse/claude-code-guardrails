# Tests for the language guard (language.py). Run: python -I hooks/tests/test_language.py
# Runs the hook the way Claude Code does (JSON on stdin, a transcript file on disk) and reads its decision.
import json, os, subprocess, sys, tempfile
sys.stdout.reconfigure(encoding='utf-8')
HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(HOOKS, 'language.py')
TMP = tempfile.mkdtemp(prefix='test_language_')
sys.path.insert(0, HOOKS)
import language  # noqa: E402
FAILURES = []

EN_TEXT = "I have finished the door and the tests are green, so we can now move to the next step."
FR_TEXT = "J'ai fini la porte et les tests sont verts, on peut passer à la suite."


def check(name, cond):
    print(('ok    ' if cond else 'FAIL  ') + name)
    if not cond:
        FAILURES.append(name)


def transcript(*entries):
    p = os.path.join(TMP, f't{len(os.listdir(TMP))}.jsonl')
    with open(p, 'w', encoding='utf-8') as f:
        for kind, content in entries:
            f.write(json.dumps({'type': kind, 'message': {'content': content}}) + '\n')
    return p


def run(path, active=False):
    data = json.dumps({'transcript_path': path, 'stop_hook_active': active}).encode('utf-8')
    out = subprocess.run([sys.executable, '-I', HOOK], input=data, capture_output=True).stdout.decode('utf-8').strip()
    return json.loads(out) if out else None


def said(text):
    return ('assistant', [{'type': 'text', 'text': text}])


check('English prose is detected', language.is_english(EN_TEXT))
check('French prose is not', not language.is_english(FR_TEXT))
check('code in backticks and code blocks is ignored',
      not language.is_english(FR_TEXT + " `the file is in the folder` ```\nif this and that: return it to the user\n```"))
check('links are ignored', not language.is_english(FR_TEXT + ' https://example.com/the/and/you/is/are/was'))

r = run(transcript(('user', 'salut'), said(EN_TEXT)))
check('a reply in English: the turn is blocked', r and r['decision'] == 'block' and 'FRENCH' in r['reason'])
check('a reply in French: nothing', run(transcript(('user', 'salut'), said(FR_TEXT))) is None)
check('English written BEFORE her last message is not counted',
      run(transcript(said(EN_TEXT), ('user', 'salut'), said(FR_TEXT))) is None)
check('tool results do not count as her message',
      (run(transcript(('user', 'salut'), said(EN_TEXT), ('user', [{'type': 'tool_result', 'content': 'x'}]), said(FR_TEXT))) or {}).get('decision') == 'block')
check('already nudged once (stop_hook_active): no loop', run(transcript(('user', 'salut'), said(EN_TEXT)), active=True) is None)
check('an unreadable input never blocks', subprocess.run([sys.executable, '-I', HOOK], input=b'{not json', capture_output=True).stdout.strip() == b'')

print(f"\n{'ALL GREEN' if not FAILURES else str(len(FAILURES)) + ' FAILURE(S)'}")
sys.exit(1 if FAILURES else 0)
