"""Stage an exact local ACR context without traversing repository caches."""

import argparse
import os
from pathlib import Path
import shutil


SOURCE_PATTERNS = {
    "contracts": ("*.py", "*.sql"),
    "logistics_an_nguyen": ("*.py",),
    "care_truc": ("*.py",),
    "platform_huy": ("*.py",),
    "platform_huy/migrations": ("*.sql",),
    "deploy": ("*.py",),
}
EXACT_FILES = (
    ".dockerignore", "deploy/Dockerfile", "deploy/requirements.txt", "care_truc/schema.sql",
    "logistics_an_nguyen/ui/index.html", "logistics_an_nguyen/ui/app.js",
    "logistics_an_nguyen/ui/data.mjs", "logistics_an_nguyen/ui/styles.css",
    "data/release_main/core_14d.sqlite", "data/release_main/ops_14d.sqlite",
)
ASSET_EXTENSIONS = {".html", ".css", ".js", ".svg", ".png", ".webp", ".jpg"}
EXCLUDED_DIRECTORIES = {
    "data", "truth", "heldout", "runs", "runtime", "node_modules",
    "__pycache__", "cache", "caches", "venv", "env",
}


def _check_path(source: Path, path: Path) -> None:
    """Reject symlinks/junctions before reading files or entering directories."""
    relative = path.relative_to(source)
    current = source
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError("Symlinks and junctions are not accepted in the build context")
    if source not in path.resolve().parents:
        raise ValueError("Build input must remain inside the source directory")


def prepare_context(source: Path, output: Path) -> Path:
    """Copy only approved inputs to a fresh directory; never remove or overwrite."""
    source = Path(source).resolve()
    output = Path(output).absolute()
    resolved_output = output.resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Build context output must be a fresh directory")
    if resolved_output == source:
        raise ValueError("Build context cannot replace the source directory")
    if source in resolved_output.parents:
        relative = resolved_output.relative_to(source).parts
        if not (len(relative) > 1 and relative[0] == "runs" or
                len(relative) > 2 and relative[:2] == (".scratch", "runs")):
            raise ValueError("Within source, context output must be under runs or .scratch/runs")

    inputs = set()
    for relative in EXACT_FILES:
        candidate = source / relative
        _check_path(source, candidate)
        if not candidate.is_file():
            raise FileNotFoundError("Required build input is missing: " + relative)
        inputs.add(candidate)
    for directory, patterns in SOURCE_PATTERNS.items():
        folder = source / directory
        _check_path(source, folder)
        for pattern in patterns:
            for candidate in folder.glob(pattern):
                _check_path(source, candidate)
                if candidate.is_file() and not candidate.name.startswith("."):
                    inputs.add(candidate)

    assets = source / "platform_huy/ui_prototype"
    _check_path(source, assets)
    for directory, subdirs, filenames in os.walk(assets, followlinks=False):
        folder = Path(directory)
        subdirs[:] = [name for name in subdirs if not name.startswith(".")
                      and name.casefold() not in EXCLUDED_DIRECTORIES]
        for name in subdirs:
            _check_path(source, folder / name)
        for name in filenames:
            candidate = folder / name
            if not name.startswith(".") and candidate.suffix.casefold() in ASSET_EXTENSIONS:
                _check_path(source, candidate)
                inputs.add(candidate)

    # Validate every input before creating the destination; copy with exclusive opens.
    output.mkdir(parents=True, exist_ok=False)
    for candidate in sorted(inputs):
        destination = output / candidate.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with candidate.open("rb") as incoming, destination.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        output = prepare_context(arguments.source, arguments.output)
    except (OSError, ValueError) as error:
        parser.exit(1, "Context preparation failed: " + str(error) + "\n")
    count = sum(1 for path in output.rglob("*") if path.is_file())
    print(f"Prepared {count} files in {output}")


if __name__ == "__main__":
    main()
