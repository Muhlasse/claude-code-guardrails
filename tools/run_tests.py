"""Runs every hook test file (hooks/tests/test_*.py) and prints one line per file.

    python -I tools/run_tests.py        -> exit 0 only if every file passes

Each test file is a plain script (Python stdlib only, no pytest): it prints "ok" or "FAIL" per check and exits 1 on
any failure. Every test writes into its own temporary folder, never into the real state folder.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    failed = 0
    total_ok = total_fail = 0
    for test in sorted((ROOT / "hooks" / "tests").glob("test_*.py")):
        p = subprocess.run([sys.executable, "-I", str(test)], capture_output=True)
        out = p.stdout.decode("utf-8", "replace").splitlines()
        ok = sum(1 for l in out if l.startswith("ok"))
        fail = sum(1 for l in out if l.startswith("FAIL"))
        total_ok += ok
        total_fail += fail
        status = "PASS" if p.returncode == 0 else "FAIL"
        failed += p.returncode != 0
        print(f"{status}  {test.name:24} {ok} checks ok, {fail} failed")
        if p.returncode:
            print("\n".join(l for l in out if l.startswith("FAIL")))
            print(p.stderr.decode("utf-8", "replace"))
    print(f"\n{total_ok} checks ok, {total_fail} failed, {failed} file(s) failing")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
