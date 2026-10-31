"""Validate runtime inputs, then launch the existing UI module on the Space port."""

import os
from pathlib import Path
import runpy
import sys

from platform_huy.a3_demo import project_root, release_dir

from .fetch_data import ReleaseError, ensure_release


def validate_state_path(release: Path, state: Path) -> Path:
    """Keep runtime outside release inputs, including symlink/hardlink aliases."""
    release, state = release.resolve(), state.resolve()
    if state == release or release in state.parents:
        raise ValueError('Runtime must be outside the source release directory')
    if state.exists():
        for name in ('core_14d.sqlite', 'ops_14d.sqlite'):
            if state.samefile(release / name):
                raise ValueError('Runtime must not alias a source database')
    return state


def main() -> None:
    try:
        release = ensure_release(release_dir())
    except (ReleaseError, OSError):
        # Deliberately avoid displaying environment or transport exception text.
        raise SystemExit("Space startup failed: validate the local release or configure SEA_DATASET_REPO and HF_TOKEN.") from None
    state = Path(os.environ.get("SEA_STATE_PATH", str(project_root() / "runs/a3-demo/state.sqlite")))
    try:
        state = validate_state_path(release, state)
    except (OSError, ValueError):
        raise SystemExit('Space startup failed: runtime must be separate from both source databases.') from None
    sys.argv = ["platform_huy.serve_ui", "--host", "0.0.0.0", "--port", os.environ.get("PORT", "7860"),
                "--core-path", str(release / "core_14d.sqlite"),
                "--state-path", str(state)]
    if os.environ.get('SEA_INTEGRATED', '').lower() in ('1', 'true'):
        sys.argv.append('--integrated')
    if os.environ.get('SEA_LLM', '').lower() in ('1', 'true'):
        sys.argv.append('--llm')
    # Keep one foreground process on Windows as well as Linux for clean shutdown.
    runpy.run_module("platform_huy.serve_ui", run_name="__main__")


if __name__ == "__main__":
    main()
