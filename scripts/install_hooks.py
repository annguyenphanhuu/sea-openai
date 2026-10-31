"""Install this repository's hooks without replacing other hook configurations."""

from pathlib import Path
import subprocess


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    current = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"], cwd=root,
        capture_output=True, text=True,
    )
    if current.returncode not in (0, 1):
        raise SystemExit("Could not read core.hooksPath")
    hooks_path = (root / ".githooks").as_posix()
    if current.stdout.strip() not in ("", ".githooks", hooks_path):
        raise SystemExit("Existing core.hooksPath found; integrate hooks manually: " + current.stdout.strip())
    for name in ("pre-commit", "pre-push", "post-checkout"):
        hook = root / ".githooks" / name
        hook.chmod(hook.stat().st_mode | 0o111)
    subprocess.run(["git", "config", "--local", "core.hooksPath", hooks_path], cwd=root, check=True)
    common = subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=root, text=True,
    ).strip()
    exclude = Path(common) / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    missing = [rule for rule in ("/docs/superpowers/", "/.codegraph/", "/.worktrees/")
               if rule not in existing.splitlines()]
    if missing:
        with exclude.open("a", encoding="utf-8") as stream:
            stream.write("\n" + "\n".join(missing) + "\n")
    print("Installed commit, push, and worktree hooks. Python must be available on PATH.")


if __name__ == "__main__":
    main()
