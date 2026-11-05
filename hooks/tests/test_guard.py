"""Tests for guard.py: runs the guard the way Claude Code does (JSON on stdin) and checks the exit code.

    python -I hooks/tests/test_guard.py      -> exit 0 if everything passes

Each "false positive" case below is a real command the guard once refused by mistake; each refused case is a way
to write into a protected folder that the guard must keep catching.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

GUARD = Path(__file__).resolve().parent.parent / "guard.py"
# refusals from the tests go to a separate file, never into the real log
REFUSALS = os.path.join(tempfile.mkdtemp(prefix="test_guard_"), "refusals.jsonl")
os.environ["GUARDRAILS_REFUSALS"] = REFUSALS
for k in ("GUARDRAILS_PROTECTED_PATHS", "GUARDRAILS_PROTECTED_NAMES", "GUARDRAILS_HUMAN_ONLY", "GUARDRAILS_RESTORE"):
    os.environ.pop(k, None)    # the tests use the defaults (refs/approved, docs/story_bible)
PS, SH, BL = "PowerShell", "Bash", "mcp__blender__execute_blender_code"


def run(raw):
    p = subprocess.run([sys.executable, "-I", str(GUARD)], input=raw, capture_output=True, env=os.environ)
    return p.returncode, p.stderr.decode("utf-8", "replace").strip()


def case(tool, value):
    key = "code" if tool == BL else "command"
    return json.dumps({"tool_name": tool, "tool_input": {key: value}}).encode("utf-8")


# The first case catches an `except` that would swallow sys.exit(0).
ACCEPTED = [
    (PS, "git status"),
    (PS, r"Get-ChildItem refs\approved"),
    (SH, "git checkout -b blender-x"),
    (PS, 'tools\\commit.ps1 "msg"'),
    (PS, 'tools\\commit.ps1 "msg" -close'),
    (PS, r'& "C:\project\tools\launch_blender.ps1"'),
    (PS, "git checkout protected-ok -- refs/approved refs/approved.sha256 docs/story_bible"),
    (PS, r'Get-Content "C:\project\captures\éléphant_ü.png"'),
    (PS, r'Copy-Item "sheet_été.png" captures\approved\ '),
    (BL, 'import bpy\nimg = bpy.data.images.load(r"C:/project/refs/approved/001.jpg")'),
    (SH, "git log --oneline -5"),
    (PS, "python tools/fingerprints.py --verify"),
    # false positive: wildcard on docs/ outside the protected folder
    (SH, "sed -i '87s/Text `\\[new\\]`\\./Text `[approved]`./' docs/03_demo.md && sed -n 87p docs/03_demo.md && wc -l docs/0*.md"),
    (SH, "wc -l docs/0*.md"),
    (PS, r"Remove-Item refs\web\x\*.tmp"),
    # false positive: opening a protected image on screen
    (PS, r'Start-Process "C:\project\refs\approved\027.jpg"; Start-Process "C:\project\refs\approved\108.jpg"'),
    (PS, r"ii refs\approved\019.png"),
    # measuring the values of protected images (read-only, images only)
    (SH, '"C:/Python/bin/python.exe" tools/measure_values.py refs/approved/211.jpg refs/approved/218.jpg'),
    (PS, r"python tools\measure_values.py refs\approved\219.jpg"),
    # a contact sheet of protected images (ffmpeg reads them, writes the image elsewhere)
    (SH, "ffmpeg -y -loglevel error -i refs/approved/309.jpg -vf scale=-2:720 captures/previews/r1.png"),
    (PS, r"ffmpeg -i refs\approved\203.jpg -i refs\approved\290.jpg -filter_complex hstack captures\previews\p.png"),
    # false positive: a quoted grep pattern 'a|b' is not a pipe; cd, head, cut only read
    (SH, 'cd /c/project && grep -n -iE "terrace|stands|brutal" refs/approved/MY_REFS.md | cut -c1-180 | head -50'),
    (SH, "ls refs/approved | grep -E '^(211|218)\\.'"),
]
REFUSED = [
    (SH, "grep -E 'a|b' refs/approved/MY_REFS.md | rm refs/approved/001.jpg"),
    (SH, "cd refs/approved; rm 001.jpg"),
    (SH, "grep 'x' refs/approved/MY_REFS.md; echo 'a|b' > refs/approved/y.md"),
    (SH, "cat refs/approved/MY_REFS.md | tail -5 > copy.txt"),
    (SH, 'grep \\" refs/approved/MY_REFS.md; rm refs/approved/001.jpg; echo \\"'),
    (SH, "grep 'x refs/approved/MY_REFS.md; rm refs/approved/001.jpg"),
    (PS, "blender -b x.py"),
    (SH, "blender -b x.py"),
    (PS, r'cd x; & "C:\Program Files\Blender\blender.exe" -b y.py'),
    (PS, "BLENDER.EXE --background"),
    (PS, "Start-Process blender -ArgumentList '-b x.py'"),
    (PS, r"Remove-Item refs\approved\001.jpg"),
    (PS, "Copy-Item a.jpg refs/approved/"),
    (PS, r"attrib -R docs\story_bible\bible.md"),
    (PS, r"Get-ChildItem refs\approved | Remove-Item"),
    (PS, r"cat x; Remove-Item refs\approved\a.jpg"),
    (PS, r"Get-Content refs\approved\MY_REFS.md > y.txt"),
    (PS, "Remove-Item refs/app*"),
    (PS, r"Remove-Item refs\*"),
    (SH, "rm -rf docs/*"),
    (SH, "rm -rf docs/sto*"),
    (SH, "rm -rf docs/[s]tory*"),
    (SH, "rm docs/st?ry_bible/x.md"),
    (PS, r"Start-Process refs\approved\x.ps1"),
    (PS, r"Start-Process mspaint refs\approved\027.jpg"),
    (PS, r"Start-Process refs\approved\027.jpg -Verb Edit"),
    (PS, r"tools\add_ref.ps1 a.jpg"),
    (SH, 'git add -A -- . ":!refs/approved"'),
    (SH, "python tools/measure_values.py refs/approved/211.jpg --small refs/approved"),
    (SH, "python tools/measure_values.py refs/approved"),
    (SH, "python tools/other.py refs/approved/211.jpg"),
    (SH, "python tools/measure_values.py refs/approved/211.jpg > refs/approved/x.txt"),
    (SH, "ffmpeg -y -i captures/a.png refs/approved/309.jpg"),
    (SH, "ffmpeg -i refs/approved/309.jpg refs/approved/x.png"),
    (SH, "ffmpeg -i x.png -vf movie=refs/approved/309.jpg out.png"),
    (SH, "ffmpeg -i refs/approved/309.jpg out.mp4"),
    (SH, "ffmpeg -i refs/approved/309.jpg out.png > refs/approved/log.txt"),
    (SH, "ffmpeg -i refs/approved/309.jpg -y refs/approved/309.jpg"),
    (BL, 'import os\nos.remove("C:/project/refs/approved/001.jpg")'),
    (BL, 'import subprocess\nsubprocess.run(["cmd"])'),
    (BL, 'img.save_render("C:/project/refs/approved/x.png")'),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    failures = 0
    for expected, cases in ((0, ACCEPTED), (2, REFUSED)):
        for tool, val in cases:
            code, err = run(case(tool, val))
            ok = code == expected
            failures += not ok
            print(f"{'ok  ' if ok else 'FAIL'} [{code}] {tool:10} {val!r}" + ("" if ok else f"  <- {err}"))
    for name, raw in (("unreadable JSON", b"{not json"),
                      ("forced exception (tool_input without command)", b'{"tool_name":"Bash","tool_input":{}}')):
        code, err = run(raw)
        ok = code == 2
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'} [{code}] {name}  <- {err}")
    # every refusal is logged, and an accepted command leaves no line
    try:
        lines = [json.loads(l) for l in open(REFUSALS, encoding="utf-8")]
    except OSError:
        lines = []
    ok = bool(lines) and all(l.get("guard") == "guard" and l.get("reason") and l.get("when") for l in lines)
    failures += not ok
    print(f"{'ok  ' if ok else 'FAIL'} refusals are written to the log ({len(lines)} lines)")
    before = len(lines)
    run(case(SH, "git status"))
    try:
        after = sum(1 for _ in open(REFUSALS, encoding="utf-8"))
    except OSError:
        after = 0
    ok = after == before
    failures += not ok
    print(f"{'ok  ' if ok else 'FAIL'} an accepted command is not logged")
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
