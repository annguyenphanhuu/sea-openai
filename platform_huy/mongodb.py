"""MongoDB configuration and managed connections for application code."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
from typing import Any

from dotenv import dotenv_values
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError


@dataclass(frozen=True, slots=True)
class MongoSettings:
    uri: str = field(repr=False)
    database: str = "sea_openai"
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.uri.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGODB_URI must be a MongoDB connection URI.")
        if not self.database or any(char in self.database for char in '/\\. "$\x00'):
            raise ValueError("MONGODB_DATABASE must be a valid database name.")
        if (self.username is None) != (self.password is None):
            raise ValueError("Set both MONGODB_USERNAME and MONGODB_PASSWORD, or neither.")


def load_mongo_settings(env_path: Path | None = None) -> MongoSettings:
    path = env_path if env_path is not None else Path(__file__).resolve().parents[1] / ".env"
    values = {**dotenv_values(path, interpolate=False), **os.environ}
    return MongoSettings(
        uri=(values.get("MONGODB_URI") or "").strip(),
        database=(values.get("MONGODB_DATABASE") or "sea_openai").strip(),
        username=values.get("MONGODB_USERNAME") or None,
        password=values.get("MONGODB_PASSWORD") or None,
    )


@contextmanager
def mongo_database(settings: MongoSettings | None = None) -> Iterator[Database[Any]]:
    config = settings if settings is not None else load_mongo_settings()
    credentials = (
        {"username": config.username, "password": config.password}
        if config.username is not None
        else {}
    )
    client: MongoClient[Any] = MongoClient(
        config.uri,
        **credentials,
        tz_aware=True,
        timeoutMS=5000,
        connectTimeoutMS=5000,
        serverSelectionTimeoutMS=5000,
    )
    try:
        yield client[config.database]
    finally:
        client.close()


def main() -> int:
    try:
        with mongo_database() as database:
            database.command("ping")
    except (ValueError, PyMongoError):
        print(
            "MongoDB connection failed. Check .env configuration, credentials, "
            "network access, and the MongoDB IP allowlist.",
            file=sys.stderr,
        )
        return 1
    print("MongoDB connection succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
