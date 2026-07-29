#!/usr/bin/env python3
"""Repository test collector for a multi-skill layout.

Two kinds of tests live in this repo and they are collected differently
because skill directories use hyphenated names (e.g. ``html-to-markdown``),
which are not importable Python package names. ``unittest discover`` relies on
package import and therefore cannot recurse into them.

1. Repository-level suite under ``tests/`` — a normal importable directory.
   Collected with ``unittest discover``.

2. Per-skill suites under ``<skill>/tests/`` — files that load their sibling
   skill modules by path (``Path(__file__).parent...``) rather than by import.
   Each file is executed as a standalone script in its own subprocess so that
   modules registered in ``sys.modules`` (e.g. ``fast_converter``) from one
   skill cannot leak into another.

Adding a new skill requires no change here: drop ``<skill>/tests/test_*.py``
into the new skill directory and it is picked up automatically. Keep the
per-skill test files runnable as scripts (define the ``unittest.main()`` guard
or an equivalent ``if __name__ == "__main__"`` entrypoint).

Exit code is non-zero if any suite fails.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROOT_SUITE_DIR = ROOT / "tests"

# Virtualenv directory names to skip when scanning for skill test dirs.
VENV_DIR_NAMES = {".venv", "venv", "env"}

# Per-skill test files run as scripts; guard against a hung test locally
# (CI also has its own job-level wall-clock timeout).
SKILL_TEST_TIMEOUT = 300


def run_root_suite() -> bool:
    """Run the repository-level tests/ suite via unittest discover."""
    if not ROOT_SUITE_DIR.is_dir():
        return True
    print("=== repository suite: tests/ ===", flush=True)
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=str(ROOT_SUITE_DIR),
        pattern="test_*.py",
        top_level_dir=str(ROOT_SUITE_DIR),
    )
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    return result.wasSuccessful()


def find_skill_test_files() -> list[Path]:
    """Find test_*.py under every <skill>/tests/, excluding the root tests/."""
    files: list[Path] = []
    for tests_dir in sorted(ROOT.glob("*/tests")):
        if not tests_dir.is_dir():
            continue
        # ROOT/tests is handled by run_root_suite; skip anything under it.
        if tests_dir.resolve() == ROOT_SUITE_DIR.resolve():
            continue
        if VENV_DIR_NAMES & set(tests_dir.parts):
            continue
        files.extend(sorted(tests_dir.glob("test_*.py")))
    return files


def run_skill_suites() -> bool:
    """Run each per-skill test file as an isolated subprocess.

    A skill test file must run its tests on import-as-script and exit non-zero
    on failure. It must also emit a recognizable "ran tests" signal on stdout
    (a ``passed`` summary, or unittest's ``Ran N``); a file that exits 0 with
    no such signal is treated as a failure, so a file of bare ``TestCase``
    classes with no ``__main__`` guard cannot silently skip everything and be
    reported green.
    """
    ok = True
    for test_file in find_skill_test_files():
        rel = test_file.relative_to(ROOT)
        print(f"=== skill suite: {rel} ===", flush=True)
        # Run from the skill directory so Path(__file__).parent resolution and
        # any relative expectations match the file's documented run command.
        try:
            proc = subprocess.run(
                [sys.executable, str(test_file.name)],
                cwd=str(test_file.parent),
                capture_output=True,
                text=True,
                timeout=SKILL_TEST_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            print(f"TIMEOUT after {SKILL_TEST_TIMEOUT}s: {rel}", flush=True)
            ok = False
            continue
        # Echo the child's own output so its per-test lines stay visible.
        if proc.stdout:
            print(proc.stdout, end="", flush=True)
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr, flush=True)
        if proc.returncode != 0:
            ok = False
            continue
        if not _ran_any_tests(proc.stdout, proc.stderr):
            print(
                f"NO TEST SIGNAL (exited 0 without running tests): {rel}",
                flush=True,
            )
            ok = False
    return ok


def _ran_any_tests(stdout: str, stderr: str) -> bool:
    """True if the child showed it actually ran tests.

    ``unittest.main()`` writes its ``Ran N tests`` / ``OK`` summary to stderr,
    while plain-assert files print a ``passed`` line to stdout — so both
    streams must be inspected or standard unittest files look like no-ops.
    """
    combined = f"{stdout}\n{stderr}"
    return bool(re.search(r"\bpassed\b|\bRan \d+ test", combined))


def main() -> int:
    root_ok = run_root_suite()
    skills_ok = run_skill_suites()
    if root_ok and skills_ok:
        print("\nALL SUITES PASSED", flush=True)
        return 0
    print("\nSOME SUITES FAILED", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
