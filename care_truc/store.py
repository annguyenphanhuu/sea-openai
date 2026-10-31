"""Single-thread SQLite writer; never keep a transaction open across an await."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .runtime_types import (CareError, CustomerEvent, PendingCancellation,
    PolicyOutcome, SessionState, TurnResult, canonical)


class MemoryStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    @classmethod
    def open(cls, path: Path) -> "MemoryStore":
        path = Path(path)
        exists = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            if exists:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("database_corrupt")
                if db.execute("SELECT schema_version FROM runtime_meta").fetchone()[0] != 1:
                    raise ValueError("unsupported_schema")
            else:
                db.executescript(Path(__file__).with_name("schema.sql").read_text())
            return cls(db)
        except BaseException:
            db.close()
            raise

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def create_session(self, state: SessionState, open_key: str) -> SessionState:
        with self.transaction():
            row = self.db.execute("SELECT id FROM sessions WHERE open_key=?", (open_key,)).fetchone()
            if row:
                return self.load_session(row[0])
            self.db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                (state.session_id, state.run_id, state.principal_id, state.order_id,
                 open_key, canonical(state), state.version))
        return state

    def load_session(self, session_id: str) -> SessionState:
        row = self.db.execute("SELECT data FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise CareError("not_found", 404)
        data = json.loads(row[0])
        if data["pending"]:
            pending = data["pending"]
            pending["expires_at"] = datetime.fromisoformat(pending["expires_at"])
            data["pending"] = PendingCancellation(**pending)
        return SessionState(**data)

    def find_request(self, session_id: str, principal: str, client_id: str):
        return self.db.execute("SELECT * FROM requests WHERE session_id=? AND principal=? AND client_id=?",
                               (session_id, principal, client_id)).fetchone()

    def request(self, request_id: str):
        return self.db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()

    def begin_request(self, session_id: str, principal_id: str, event: CustomerEvent, fingerprint: str):
        with self.transaction():
            existing = self.find_request(session_id, principal_id, event.request_id)
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise CareError("request_conflict")
                return existing
            state = self.load_session(session_id)
            internal_id = uuid4().hex
            self.db.execute("INSERT INTO requests(id,run_id,session_id,principal,client_id,fingerprint,payload,phase,base_version) VALUES(?,?,?,?,?,?,?,'processing',?)",
                (internal_id, state.run_id, session_id, principal_id, event.request_id,
                 fingerprint, canonical(event), state.version))
        return self.request(internal_id)

    def _event(self, session_id: str, event_id: str, kind: str, content: str,
               visibility: str = "customer") -> None:
        sequence = self.db.execute("SELECT coalesce(max(sequence),0)+1 FROM events WHERE session_id=?",
                                   (session_id,)).fetchone()[0]
        self.db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",
                        (event_id, session_id, sequence, visibility, kind, content))

    def commit_turn(self, request_id: str, expected_version: int, outcome: PolicyOutcome,
                    response: TurnResult, evidence: str, trace: str) -> TurnResult:
        with self.transaction():
            request = self.request(request_id)
            if request["phase"] == "committed":
                return self.response(request)
            state = replace(outcome.state, version=expected_version + 1)
            changed = self.db.execute("UPDATE sessions SET data=?,version=? WHERE id=? AND version=?",
                (canonical(state), state.version, state.session_id, expected_version)).rowcount
            if not changed:
                raise CareError("state_conflict")
            self.db.execute("INSERT INTO evidence_bundles VALUES(?,?,?,?)",
                            (request_id, request_id, evidence, trace))
            self._event(state.session_id, request_id + ":customer", "customer", request["payload"])
            self._event(state.session_id, request_id + ":response", "response", canonical(response))
            if outcome.invalidate_unsent:
                self.db.execute("UPDATE pending_effects SET state='blocked' WHERE session_id=? AND attempts=0 AND state IN ('pending_delivery','retry_wait')", (state.session_id,))
            for proposal in outcome.proposals:
                self._save_proposal(proposal, request_id, state)
            self.db.execute("UPDATE requests SET phase='committed',response=?,context=? WHERE id=?",
                            (canonical(response), evidence, request_id))
        return response

    def _save_proposal(self, proposal, request_id, state) -> None:
        self.db.execute("INSERT INTO pending_effects(id,run_id,effect_key,session_id,proposal,session_version) VALUES(?,?,?,?,?,?)",
                        (proposal.effect_id, state.run_id, proposal.key, state.session_id,
                         canonical(proposal), state.version))
        self.db.execute("INSERT INTO effect_proposals VALUES(?,1,?,?)",
                        (proposal.effect_id, request_id, canonical(proposal)))

    def events(self, session_id: str) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY sequence", (session_id,))]

    @staticmethod
    def response(row) -> TurnResult:
        data = json.loads(row["response"])
        data["codes"] = tuple(data["codes"])
        data["effect_ids"] = tuple(data["effect_ids"])
        return TurnResult(**data)

    def close(self) -> None:
        self.db.close()
