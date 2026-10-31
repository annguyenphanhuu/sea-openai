"""Verify the installed hook through actual worktree creation."""

from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def run(cwd: Path, *args: str) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=subprocess.STDOUT)


def test_worktree_creation_copies_ignored_files_without_overwriting(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    run(source, "git", "init")
    run(source, "git", "config", "user.name", "Test")
    run(source, "git", "config", "user.email", "test@example.com")
    # The branch deliberately predates the docs/superpowers ignore rule.
    (source / ".gitignore").write_text(".env\ndata/\n")
    run(source, "git", "add", ".gitignore")
    run(source, "git", "commit", "-m", "Fixture")
    for folder in ("scripts", ".githooks"):
        shutil.copytree(ROOT / folder, source / folder, ignore=shutil.ignore_patterns("__pycache__"))
    plan = source / "docs/superpowers/plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("local plan")
    (source / ".env").write_text("LOCAL_KEY=fixture")
    run(source, sys.executable, "scripts/install_hooks.py")
    run(source, sys.executable, "scripts/install_hooks.py")
    target = tmp_path / "target"
    output = run(source, "git", "worktree", "add", "--detach", str(target), "HEAD")
    assert "Copied" in output
    assert (target / "docs/superpowers/plan.md").read_text() == "local plan"
    assert (target / ".env").read_text() == "LOCAL_KEY=fixture"
    assert run(target, "git", "status", "--porcelain") == ""
    assert run(target, "git", "check-ignore", "docs/superpowers/plan.md").strip()
    # Explicit resync preserves existing destination content.
    (target / "docs/superpowers/plan.md").write_text("destination edits")
    run(target, sys.executable, str(source / "scripts/sync_worktree_ignored.py"))
    assert (target / "docs/superpowers/plan.md").read_text() == "destination edits"
    # Ordinary checkouts do not sync newly created ignored source files.
    (source / "data").mkdir()
    (source / "data/later.txt").write_text("later")
    run(target, "git", "checkout", "--detach", "HEAD")
    assert not (target / "data/later.txt").exists()
