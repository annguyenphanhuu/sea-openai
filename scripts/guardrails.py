"""Check indexed files without reading private runtime data or printing contents."""

import argparse
import os
from pathlib import PurePosixPath
import re
import subprocess
import sys


CONFLICT = re.compile(rb"^(?:<{7}|={7}|>{7}|\|{7})(?:\s|$)")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def forbidden(path: str) -> bool:
    parts = PurePosixPath(path.lower()).parts
    name = parts[-1]
    return (
        any(part in {"data", "runs", "truth", ".codegraph"} for part in parts[:-1])
        or (name != ".env.example" and (name == ".env" or name.startswith(".env.")))
        or re.search(r"\.(?:sqlite|sqlite3|db)(?:$|[-.])", name) is not None
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true", help="Check added/modified index entries")
    mode.add_argument("--all", action="store_true", help="Check every tracked index entry")
    parser.add_argument("--tests", action="store_true", help="Also import contracts and run pytest")
    args = parser.parse_args()
    root = git("rev-parse", "--show-toplevel").decode().strip()
    # Run from the root even when invoked manually from a subdirectory.
    os.chdir(root)
    raw = (git("ls-files", "-z") if args.all else
           git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"))
    errors = []
    for encoded in raw.split(b"\0"):
        if not encoded:
            continue
        path = encoded.decode("utf-8", errors="surrogateescape")
        if forbidden(path):
            errors.append(f"{path}: private data path must remain untracked")
            continue
        content = git("show", f":{path}")
        if b"\0" in content:
            continue
        for number, line in enumerate(content.splitlines(), 1):
            if CONFLICT.match(line):
                errors.append(f"{path}:{number}: unresolved conflict marker")
            if args.all and (line.endswith((b" ", b"\t")) or re.match(rb"^ *\t", line)):
                errors.append(f"{path}:{number}: whitespace error")
    if args.staged:
        if subprocess.run(["git", "diff", "--cached", "--check"], capture_output=True).returncode:
            errors.append("Fix staged whitespace errors before committing")
    if errors:
        print("Guardrails failed:\n" + "\n".join(errors))
        return 1
    if args.tests:
        for command in ([sys.executable, "-c", "import contracts"],
                        [sys.executable, "-m", "pytest", "-q"]):
            result = subprocess.run(command)
            if result.returncode:
                return result.returncode
    print("Guardrails passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Git check failed (exit {exc.returncode})", file=sys.stderr)
        sys.exit(1)
