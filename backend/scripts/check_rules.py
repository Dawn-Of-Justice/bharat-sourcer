"""Offline deployment gate for resistor rule changes, including fault recovery."""

import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    # Tests cover reference examples, current bounds, selector quarantine and fail-closed behavior.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_resistor_rules.py", "-q"],
        cwd=root,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
