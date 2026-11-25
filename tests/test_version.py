"""The version lives in three files; CI fails the build when they disagree.

This test runs the same check locally so the failure is found before pushing.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_version_files_agree():
    result = subprocess.run(
        [sys.executable, str(ROOT / 'tools' / 'bump_version.py'), '--check'],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'version in sync' in result.stdout
