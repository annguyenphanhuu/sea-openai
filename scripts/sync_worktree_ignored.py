"""Copy ignored local files to a new worktree without overwriting its files."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--on-create", nargs=3, metavar=("OLD", "NEW", "BRANCH"))
    args = parser.parse_args()
    if args.on_create:
        old, _, branch = args.on_create
        if branch != "1" or old.strip("0"):
            return
    # Git exports worktree-specific environment in hooks. Clear it before using -C.
    env = os.environ.copy()
    local_vars = subprocess.check_output(["git", "rev-parse", "--local-env-vars"], text=True)
    for key in local_vars.splitlines():
        env.pop(key, None)
    target = Path(subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True, env=env,
    ).strip()).resolve()
    source = Path(__file__).resolve().parents[1]
    if source == target:
        return
    worktrees = subprocess.check_output(
        ["git", "-C", str(source), "worktree", "list", "--porcelain"], text=True, env=env,
    )
    excluded = [Path(line[9:]).resolve() for line in worktrees.splitlines()
                if line.startswith("worktree ") and Path(line[9:]).resolve() != source]
    raw = subprocess.check_output(
        ["git", "-C", str(source), "ls-files", "--others", "--ignored", "--exclude-standard", "-z"], env=env,
    )
    copied = 0
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        relative = Path(os.fsdecode(entry))
        origin = source / relative
        destination = target / relative
        if ".git" in relative.parts or any(origin.is_relative_to(path) for path in excluded):
            continue
        if destination.exists() or destination.is_symlink():
            continue
        # Never follow a tracked destination symlink outside the new worktree.
        if not destination.resolve().is_relative_to(target):
            raise SystemExit(f"Refusing destination outside worktree: {relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, destination, follow_symlinks=False)
        copied += 1
    print(f"Copied {copied} ignored local files into {target}")


if __name__ == "__main__":
    main()
