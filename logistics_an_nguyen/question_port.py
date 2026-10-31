"""Async question repository; the local wrapper owns each operation transaction."""
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from datetime import datetime
import sqlite3
import time
from typing import Protocol

from .models import SupervisorQuestion
from .questions import QuestionStore


class QuestionConflict(ValueError):
    code = "conflict"


class QuestionStorageError(Exception):
    code = "store_unavailable"


class QuestionRepository(Protocol):
    async def save(self, questions: Iterable[SupervisorQuestion], *, deadline: float) -> None: ...
    async def list_questions(self, *, order_id: str | None = None, status: str | None = None,
                             deadline: float) -> list[dict]: ...
    async def answer(self, question_id: str, *, answer_text: str, answered_by: str,
                     answered_at: datetime, deadline: float) -> None: ...


class LocalQuestionRepository:
    def __init__(self, store: QuestionStore, *, monotonic: Callable[[], float] = time.monotonic):
        self.store = store
        self.monotonic = monotonic

    def _check(self, deadline: float) -> None:
        if self.monotonic() >= deadline:
            raise QuestionStorageError("storage_deadline_exceeded")

    @contextmanager
    def _transaction(self):
        connection = self.store.connection
        if connection.in_transaction:
            raise QuestionStorageError("repository_requires_transaction_boundary")
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    async def save(self, questions: Iterable[SupervisorQuestion], *, deadline: float) -> None:
        self._check(deadline)
        try:
            with self._transaction():
                self.store.save(questions)
        except sqlite3.DatabaseError as error:
            raise QuestionStorageError() from error

    async def list_questions(self, *, order_id: str | None = None, status: str | None = None,
                             deadline: float) -> list[dict]:
        self._check(deadline)
        try:
            return self.store.list_questions(order_id=order_id, status=status)
        except sqlite3.DatabaseError as error:
            raise QuestionStorageError() from error

    async def answer(self, question_id: str, *, answer_text: str, answered_by: str,
                     answered_at: datetime, deadline: float) -> None:
        self._check(deadline)
        try:
            with self._transaction():
                self.store.answer(question_id, answer_text=answer_text,
                                  answered_by=answered_by, answered_at=answered_at)
        except ValueError as error:
            if str(error) == "question already answered":
                raise QuestionConflict(str(error)) from error
            raise
        except sqlite3.DatabaseError as error:
            raise QuestionStorageError() from error
