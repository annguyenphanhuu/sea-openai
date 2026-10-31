"""Supervisor question persistence on the existing runtime schema only."""

import json
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Iterable

from .models import SupervisorQuestion, aware, nonempty, parse_instant, utc_iso
from .service import evidence_payload


class QuestionStore:
    """Use an in-memory database or runs/ state; the caller owns transactions.

    Platform must authenticate and authorize the supervisor before calling answer.
    An answer is a review record, never a logistics fact or financial instruction.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        databases = connection.execute("PRAGMA database_list").fetchall()
        main_path = next(row[2] for row in databases if row[1] == "main")
        runtime_root = Path(__file__).resolve().parents[1] / "runs"
        if main_path and not Path(main_path).resolve().is_relative_to(runtime_root.resolve()):
            raise ValueError("persistent A2 state must be under the repository runs/ directory")
        self.connection = connection

    def save(self, questions: Iterable[SupervisorQuestion]) -> None:
        rows = [(
            question.question_id, question.order_id, question.question_text,
            json.dumps(evidence_payload(question.evidence), ensure_ascii=False, allow_nan=False),
            utc_iso(question.asked_at),
        ) for question in questions]
        self.connection.executemany(
            "INSERT INTO main.supervisor_questions "
            "(question_id, order_id, question_text, evidence_json, asked_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(question_id) DO NOTHING", rows,
        )

    def list_questions(self, *, order_id: str | None = None, status: str | None = None) -> list[dict]:
        if status not in (None, "open", "answered"):
            raise ValueError("status must be open or answered")
        cursor = self.connection.execute(
            "SELECT question_id, order_id, asked_by, question_text, evidence_json, "
            "asked_at, status, answer_text, answered_at, answered_by "
            "FROM main.supervisor_questions WHERE (? IS NULL OR order_id = ?) "
            "AND (? IS NULL OR status = ?) ORDER BY asked_at, question_id",
            (order_id, order_id, status, status),
        )
        names = [item[0] for item in cursor.description]
        result = []
        for row in cursor:
            item = dict(zip(names, row))
            item["evidence"] = json.loads(item.pop("evidence_json"))
            result.append(item)
        return result

    def answer(
        self, question_id: str, *, answer_text: str,
        answered_by: str, answered_at: datetime,
    ) -> None:
        nonempty(question_id, "question_id")
        nonempty(answer_text, "answer_text")
        nonempty(answered_by, "answered_by")
        aware(answered_at, "answered_at")
        row = self.connection.execute(
            "SELECT asked_at, status, answer_text, answered_by "
            "FROM main.supervisor_questions WHERE question_id = ?", (question_id,),
        ).fetchone()
        if row is None:
            raise KeyError(question_id)
        if answered_at < parse_instant(row[0], "asked_at"):
            raise ValueError("answer cannot precede the question")
        if row[1] == "answered":
            if (answer_text, answered_by) == (row[2], row[3]):
                return
            raise ValueError("question already answered")
        cursor = self.connection.execute(
            "UPDATE main.supervisor_questions SET status = 'answered', answer_text = ?, "
            "answered_at = ?, answered_by = ? WHERE question_id = ? AND status = 'open'",
            (answer_text, utc_iso(answered_at), answered_by, question_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("question already answered")
