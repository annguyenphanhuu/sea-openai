"""Require task branches named <type>/<lowercase-kebab-description>."""

import re
import subprocess
import sys


PATTERN = re.compile(
    r"(?:feat|fix|chore|docs|refactor|test|perf|build|ci|revert)/[a-z0-9]+(?:-[a-z0-9]+)*"
)


def main() -> int:
    if len(sys.argv) > 2:
        print("Usage: python scripts/check_branch.py [branch]", file=sys.stderr)
        return 1
    if len(sys.argv) == 2:
        branch = sys.argv[1]
    else:
        result = subprocess.run(
            ["git", "symbolic-ref", "--quiet", "--short", "HEAD"],
            capture_output=True, text=True,
        )
        branch = result.stdout.strip() if result.returncode == 0 else ""
    if not PATTERN.fullmatch(branch):
        print(
            "Branch rejected. Use <type>/<lowercase-kebab-description>, e.g. "
            "chore/repository-guardrails. Types: feat, fix, chore, docs, refactor, "
            "test, perf, build, ci, revert. Direct commits/pushes from main or "
            "a detached HEAD are blocked."
        )
        return 1
    print(f"Branch name passed: {branch}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
