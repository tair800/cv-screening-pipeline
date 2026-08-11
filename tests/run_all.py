"""Run every offline test. No API key, no network, no cost.

Run:
    python tests/run_all.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

SUITES = [
    "test_validation.py",
    "test_parse.py",
    "test_alias_matching.py",
    "test_decisions.py",
    "test_bias_parity.py",
]


def main() -> None:
    results = []
    for suite in SUITES:
        completed = subprocess.run(
            [sys.executable, str(HERE / suite)],
            capture_output=True, text=True,
        )
        passed = completed.returncode == 0
        results.append((suite, passed))
        print(f"{'PASS' if passed else 'FAIL'}  {suite}")
        if not passed:
            print(completed.stdout[-2000:])
            print(completed.stderr[-2000:])

    failed = [name for name, passed in results if not passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} suites passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
