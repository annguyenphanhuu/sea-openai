"""Guard the Azure build boundary; actual image execution is checked in ACR."""

from pathlib import Path
import shlex


ROOT = Path(__file__).resolve().parents[1]


def docker_instructions():
    text = (ROOT / "deploy/Dockerfile").read_text(encoding="utf-8")
    return [shlex.split(line) for line in text.replace("\\\n", " ").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def ignore_rules():
    return [line.strip() for line in (ROOT / ".dockerignore").read_text(
        encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def test_image_copies_only_application_and_the_two_approved_release_files():
    """A broad COPY or a third release artifact must fail the build policy."""
    copies = [line for line in docker_instructions() if line[0] == "COPY"]
    assert all(line[1] == "--chown=app:app" for line in copies)
    assert [line[2:-1] for line in copies] == [
        ["deploy/requirements.txt"],
        ["contracts/*.py", "contracts/*.sql"],
        ["logistics_an_nguyen/*.py"],
        ["logistics_an_nguyen/ui/index.html", "logistics_an_nguyen/ui/app.js",
         "logistics_an_nguyen/ui/data.mjs", "logistics_an_nguyen/ui/styles.css"],
        ["care_truc/*.py", "care_truc/schema.sql"],
        ["platform_huy/*.py"],
        ["platform_huy/migrations/*.sql"],
        ["platform_huy/ui_prototype/"],
        ["deploy/*.py"],
        ["data/release_main/core_14d.sqlite", "data/release_main/ops_14d.sqlite"],
    ]
    assert copies[-1][-1] == "${SEA_RELEASE_DIR}/"
    assert not any(line[0] == "ADD" for line in docker_instructions())


def test_embedded_sources_are_read_only_and_runtime_is_separate():
    instructions = docker_instructions()
    environment = dict(item.split("=", 1) for line in instructions
                       if line[0] == "ENV" for item in line[1:])
    assert environment["SEA_RELEASE_DIR"] == "/home/app/app/data/release_main"
    assert environment["SEA_STATE_PATH"] == "/home/app/app/runs/integrated-demo/state.sqlite"
    assert ["RUN", "chmod", "0444", "${SEA_RELEASE_DIR}/core_14d.sqlite",
            "${SEA_RELEASE_DIR}/ops_14d.sqlite"] in instructions
    assert [line for line in instructions if line[0] == "USER"][-1] == ["USER", "app"]


def test_build_context_has_no_unapproved_inclusion_rules():
    """Fail if a future exception admits secrets, datasets or unrelated source."""
    rules = ignore_rules()
    assert rules[0] == "**"
    assert [line for line in rules if line.startswith("!")] == [
        "!contracts/", "!contracts/*.py", "!contracts/*.sql",
        "!logistics_an_nguyen/", "!logistics_an_nguyen/*.py",
        "!logistics_an_nguyen/ui/", "!logistics_an_nguyen/ui/index.html",
        "!logistics_an_nguyen/ui/app.js", "!logistics_an_nguyen/ui/data.mjs",
        "!logistics_an_nguyen/ui/styles.css",
        "!care_truc/", "!care_truc/*.py", "!care_truc/schema.sql",
        "!platform_huy/", "!platform_huy/*.py", "!platform_huy/migrations/",
        "!platform_huy/migrations/*.sql", "!platform_huy/ui_prototype/",
        "!platform_huy/ui_prototype/**", "!deploy/", "!deploy/*.py",
        "!deploy/requirements.txt", "!deploy/Dockerfile",
        "!data/", "!data/release_main/",
        "!data/release_main/core_14d.sqlite", "!data/release_main/ops_14d.sqlite",
    ]


def test_nested_secrets_and_runtime_stay_excluded_before_exact_data_exceptions():
    rules = ignore_rules()
    source_end = rules.index("!deploy/Dockerfile")
    data_start = rules.index("!data/")
    for sensitive in (
        "**/.env*", "**/*.token", "**/data", "**/truth", "**/heldout",
        "**/runs", "**/runtime", "**/.git", "**/.worktrees", "**/.scratch",
        "**/__pycache__", "**/*.pyc", "**/*.sqlite", "**/*.sqlite-*", "**/*.db",
    ):
        assert source_end < rules.index(sensitive) < data_start
    # Opening directories must not implicitly open their other contents.
    assert rules[data_start:] == [
        "!data/", "data/*", "!data/release_main/", "data/release_main/*",
        "!data/release_main/core_14d.sqlite", "!data/release_main/ops_14d.sqlite",
    ]


def test_opening_source_directories_does_not_admit_unlisted_siblings():
    rules = ignore_rules()
    for directory in (
        "contracts", "logistics_an_nguyen", "logistics_an_nguyen/ui", "care_truc", "platform_huy",
        "platform_huy/migrations", "deploy",
    ):
        assert rules[rules.index("!" + directory + "/") + 1] == directory + "/**"


def test_orders_context_excludes_unapproved_sentinel_json(tmp_path):
    from acceptance_huy.test_azure_context import fixture_source
    from deploy.prepare_context import prepare_context

    source = fixture_source(tmp_path)
    sentinel = source / "logistics_an_nguyen/ui/sentinel.json"
    sentinel.write_bytes(b"unapproved fixture")
    output = tmp_path / "context"
    prepare_context(source, output)
    assert not (output / "logistics_an_nguyen/ui/sentinel.json").exists()
    assert (output / "logistics_an_nguyen/ui/index.html").read_bytes() == b"orders"
