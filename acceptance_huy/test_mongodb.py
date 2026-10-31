from contextlib import contextmanager
from pathlib import Path

import pytest
from pymongo.errors import OperationFailure

from platform_huy import mongodb


@pytest.fixture(autouse=True)
def isolated_mongo_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MONGODB_URI", "MONGODB_DATABASE", "MONGODB_USERNAME", "MONGODB_PASSWORD"):
        monkeypatch.delenv(name, raising=False)


def test_settings_read_dotenv_without_mutating_environment(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "MONGODB_URI=mongodb://localhost:27017\n"
        "MONGODB_USERNAME=user\nMONGODB_PASSWORD='p@ss:${SECRET}'\n",
        encoding="utf-8",
    )
    settings = mongodb.load_mongo_settings(path)
    assert settings.database == "sea_openai"
    assert settings.password == "p@ss:${SECRET}"
    assert "MONGODB_URI" not in mongodb.os.environ


def test_environment_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / ".env"
    path.write_text("MONGODB_URI=mongodb://file\nMONGODB_DATABASE=file_db\n", encoding="utf-8")
    monkeypatch.setenv("MONGODB_URI", "mongodb://environment")
    monkeypatch.setenv("MONGODB_DATABASE", "environment_db")
    settings = mongodb.load_mongo_settings(path)
    assert settings.uri == "mongodb://environment"
    assert settings.database == "environment_db"


def test_default_dotenv_is_relative_to_module_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    (root / ".env").write_text("MONGODB_URI=mongodb://repository\n", encoding="utf-8")
    monkeypatch.setattr(mongodb, "__file__", str(root / "platform_huy" / "mongodb.py"))
    monkeypatch.chdir(tmp_path)
    assert mongodb.load_mongo_settings().uri == "mongodb://repository"


@pytest.mark.parametrize("uri", ["", "https://secret-user:secret-password@host"])
def test_invalid_uri_error_does_not_expose_credentials(uri: str) -> None:
    with pytest.raises(ValueError, match="MONGODB_URI") as error:
        mongodb.MongoSettings(uri=uri)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("database", ["", "has space", "with.dot", "with/slash", "with\x00null"])
def test_invalid_database_is_rejected(database: str) -> None:
    with pytest.raises(ValueError, match="MONGODB_DATABASE"):
        mongodb.MongoSettings(uri="mongodb://localhost", database=database)


def test_credentials_must_be_supplied_together() -> None:
    with pytest.raises(ValueError, match="both"):
        mongodb.MongoSettings(uri="mongodb://localhost", username="user")


def test_settings_repr_hides_connection_secrets() -> None:
    settings = mongodb.MongoSettings(
        uri="mongodb://embedded:secret@host", username="other-user", password="other-secret",
    )
    assert repr(settings) == "MongoSettings(database='sea_openai')"


def test_connection_preserves_raw_credentials_and_closes_after_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    database = object()

    class Client:
        def __init__(self, uri: str, **options: object) -> None:
            captured.update(uri=uri, options=options, closed=False)

        def __getitem__(self, name: str) -> object:
            captured["database"] = name
            return database

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(mongodb, "MongoClient", Client)
    settings = mongodb.MongoSettings(
        uri="mongodb://host", username="u@:/", password="p@:/+#${VALUE}",
    )
    with pytest.raises(RuntimeError, match="application failure"):
        with mongodb.mongo_database(settings) as connected:
            assert connected is database
            raise RuntimeError("application failure")
    assert captured["closed"] is True
    assert captured["database"] == "sea_openai"
    assert captured["options"] == {
        "username": "u@:/", "password": "p@:/+#${VALUE}", "tz_aware": True,
        "timeoutMS": 5000, "connectTimeoutMS": 5000, "serverSelectionTimeoutMS": 5000,
    }


def test_embedded_credentials_are_passed_without_empty_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Client:
        def __init__(self, uri: str, **options: object) -> None:
            captured.update(uri=uri, options=options, closed=False)

        def __getitem__(self, name: str) -> None:
            return None

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(mongodb, "MongoClient", Client)
    uri = "mongodb://user:password@host"
    with mongodb.mongo_database(mongodb.MongoSettings(uri=uri)):
        pass
    assert captured["uri"] == uri
    assert "username" not in captured["options"]
    assert "password" not in captured["options"]
    assert captured["closed"] is True


def test_cli_ping_success(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    commands: list[str] = []

    class Database:
        def command(self, command: str) -> None:
            commands.append(command)

    @contextmanager
    def connection():
        yield Database()

    monkeypatch.setattr(mongodb, "mongo_database", connection)
    assert mongodb.main() == 0
    assert commands == ["ping"]
    assert capsys.readouterr().out == "MongoDB connection succeeded.\n"


def test_cli_failure_does_not_print_driver_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    @contextmanager
    def connection():
        raise OperationFailure("mongodb://secret-user:secret-password@host")
        yield

    monkeypatch.setattr(mongodb, "mongo_database", connection)
    assert mongodb.main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "MongoDB connection failed" in output.err
    assert "secret" not in output.err
