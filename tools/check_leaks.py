"""Run before every publication: fails if a private detail appears in any file of the repository.

    python -I tools/check_leaks.py        -> exit 0 if clean, 1 with the list of hits otherwise

Two word lists, matched case-insensitively against every file (content and name) under the repository root, except .git/:
  - GENERIC below: secrets and machine paths that must never be published;
  - the private list, one word per line, in `.leak_words.txt` at the repository root. That file names the very things
    that must stay private (people, places, accounts), so it is never committed: the script fails if git does not
    ignore it, and fails if it is missing (a check without its list would pass for nothing).
Words in GENERIC are split with "+" so that this file does not match itself.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_LIST = ROOT / ".leak_words.txt"
GENERIC = ["sk-" + "ant", "o" + "auth", "token" + ".txt", "Users" + "\\", "/" + "Users/", "C:" + "\\Users",
           "BEGIN " + "PRIVATE KEY", "api" + "_key="]
# Words allowed in one file only (the author's name in the licence).
ALLOWED_IN = {"LICENSE": {"car" + "ina", "chir" + "outer"}}


def private_words():
    try:
        return [w.strip() for w in PRIVATE_LIST.read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")]
    except OSError:
        return None


def is_git_ignored(path):
    p = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT, capture_output=True)
    return p.returncode == 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    words = private_words()
    if words is None:
        print(f"FAIL: {PRIVATE_LIST.name} is missing: the private word list must exist locally before publishing.")
        return 1
    if not is_git_ignored(PRIVATE_LIST):
        print(f"FAIL: {PRIVATE_LIST.name} is not ignored by git: add it to .gitignore, it must never be published.")
        return 1
    needles = [(w, w.lower()) for w in GENERIC + words]
    hits = []
    for f in sorted(ROOT.rglob("*")):
        rel = f.relative_to(ROOT)
        if not f.is_file() or ".git" in rel.parts or f == PRIVATE_LIST or "__pycache__" in rel.parts:
            continue
        low = f.read_bytes().decode("utf-8", "replace").lower()
        allowed = ALLOWED_IN.get(str(rel).replace("\\", "/"), set())
        for i, line in enumerate(low.splitlines(), 1):
            for w, n in needles:
                if n in line and n not in allowed:
                    hits.append(f"{rel}:{i}: forbidden word #{needles.index((w, n)) + 1}")
        for w, n in needles:
            if n in str(rel).lower():
                hits.append(f"{rel}: forbidden word #{needles.index((w, n)) + 1} in the file name")
    if hits:
        print("LEAKS FOUND (word numbers refer to GENERIC then .leak_words.txt):")
        print("\n".join(hits))
        return 1
    print(f"clean: {len(needles)} forbidden words checked, none found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
