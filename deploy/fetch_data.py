"""Fetch only immutable release inputs, publishing no partial downloads."""

from contextlib import closing
from hashlib import sha256
import os
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory

REQUIRED_FILES = ("core_14d.sqlite", "ops_14d.sqlite")
ALLOW_PATTERNS = ["release_main/core_14d.sqlite", "release_main/ops_14d.sqlite",
                  "release_main/manifest.sha256"]


class ReleaseError(RuntimeError):
    """A release is unavailable, incomplete or invalid."""


def validate_release(directory: Path) -> Path:
    """Check both SQLite inputs read-only, including hashes when supplied."""
    directory = directory.resolve()
    try:
        for name in REQUIRED_FILES:
            path = directory / name
            if not path.is_file() or path.stat().st_size == 0:
                raise ReleaseError(f"Release is missing required file: {name}")
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
                connection.execute("PRAGMA query_only=ON")
                if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise ReleaseError(f"SQLite integrity check failed: {name}")
        manifest = directory / "manifest.sha256"
        if manifest.exists():
            expected = {}
            for line in manifest.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(.+)", line)
                if match is None:
                    raise ReleaseError("Invalid release checksum manifest")
                digest, filename = match.groups()
                if filename in REQUIRED_FILES:
                    if filename in expected:
                        raise ReleaseError("Duplicate release checksum entry")
                    expected[filename] = digest.lower()
            for name in REQUIRED_FILES:
                if name not in expected:
                    raise ReleaseError(f"Manifest is missing checksum: {name}")
                digest = sha256()
                with (directory / name).open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected[name]:
                    raise ReleaseError(f"Release checksum mismatch: {name}")
    except (OSError, UnicodeError, sqlite3.Error):
        raise ReleaseError("Release files are unreadable or invalid SQLite") from None
    return directory


def ensure_release(directory: Path) -> Path:
    """Reuse a valid offline release or stage a tightly filtered private snapshot.

    Existing invalid directories fail closed. The operator must choose a new
    directory or explicitly repair the offline release before restarting.
    """
    directory = Path(directory).resolve()
    if directory.exists():
        return validate_release(directory)
    repo_id = os.environ.get("SEA_DATASET_REPO", "").strip()
    if not repo_id:
        raise ReleaseError("SEA_DATASET_REPO is required when no local release exists")
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        raise ReleaseError("HF_TOKEN runtime secret is required for the private dataset")
    try:
        # Keep the common application/test import path independent of this extra.
        from huggingface_hub import snapshot_download
    except ImportError:
        raise ReleaseError("Install deploy/requirements.txt to download release data") from None
    directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".sea-release-", dir=directory.parent) as temporary:
        staging = Path(temporary)
        try:
            snapshot_download(repo_id=repo_id, repo_type="dataset", token=token,
                              revision=os.environ.get("SEA_DATASET_REVISION", "main"),
                              local_dir=str(staging), allow_patterns=list(ALLOW_PATTERNS))
        except Exception:
            # Hub transport exceptions can contain request/credential details.
            raise ReleaseError("Private release download failed; check dataset configuration and access") from None
        ready = validate_release(staging / "release_main")
        try:
            # Same filesystem sibling rename publishes the validated pair together.
            ready.replace(directory)
        except OSError:
            raise ReleaseError("Cannot publish release directory; no server was started") from None
    return directory


def main() -> None:
    from platform_huy.a3_demo import release_dir
    try:
        ensure_release(release_dir())
    except ReleaseError as error:
        raise SystemExit(str(error)) from None
    print("Release inputs validated.", flush=True)


if __name__ == "__main__":
    main()
