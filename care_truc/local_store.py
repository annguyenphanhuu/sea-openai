"""Local async CareStore adapter over the compatible synchronous SQLite store."""
from collections.abc import Callable
from functools import wraps
import sqlite3
import time

from .runtime_types import (AttemptToken, CustomerEvent, EffectProposal, HookDecision,
    PolicyOutcome, Receipt, SessionState, TurnResult)
from .storage_port import (EffectRecord, EventRecord, EvidenceRecord, RequestRecord, StorageError)
from .store import MemoryStore


def local_operation(method):
    @wraps(method)
    async def call(self, *args, deadline: float, **kwargs):
        if self.monotonic() >= deadline:
            raise StorageError("storage_deadline_exceeded")
        try:
            return await method(self, *args, deadline=deadline, **kwargs)
        except (sqlite3.DatabaseError, OSError) as error:
            raise StorageError("store_unavailable") from error
    return call


class LocalCareStore:
    def __init__(self, store: MemoryStore, *, monotonic: Callable[[], float] = time.monotonic):
        self.local = store
        self.monotonic = monotonic

    def cached_local_health(self) -> tuple[int, int]:
        try:
            return self.local.health_counts()
        except sqlite3.DatabaseError as error:
            raise StorageError("store_unavailable") from error

    @staticmethod
    def response(row: RequestRecord) -> TurnResult:
        return MemoryStore.response(row)

    @local_operation
    async def create_session(self, state: SessionState, open_key: str, *, deadline: float) -> SessionState:
        return self.local.create_session(state, open_key)

    @local_operation
    async def load_session(self, session_id: str, *, deadline: float) -> SessionState:
        return self.local.load_session(session_id)

    @local_operation
    async def find_request(self, session_id: str, principal: str, client_id: str, *, deadline: float) -> RequestRecord | None:
        row = self.local.find_request(session_id, principal, client_id)
        return dict(row) if row is not None else None

    @local_operation
    async def request(self, request_id: str, *, deadline: float) -> RequestRecord:
        return dict(self.local.request(request_id))

    @local_operation
    async def begin_request(self, session_id: str, principal_id: str, event: CustomerEvent, fingerprint: str, *, deadline: float) -> RequestRecord:
        return dict(self.local.begin_request(session_id, principal_id, event, fingerprint))

    @local_operation
    async def commit_turn(self, request_id: str, expected_version: int, outcome: PolicyOutcome, response: TurnResult, evidence: str, trace: str, *, token: AttemptToken, deadline: float) -> TurnResult | bool:
        return self.local.commit_turn(request_id, expected_version, outcome, response, evidence, trace, token=token)

    @local_operation
    async def reserve_processing(self, request_id: str, boot_generation: int, now: float = 0, *, deadline: float) -> AttemptToken | None:
        return self.local.reserve_processing(request_id, boot_generation, now)

    @local_operation
    async def reserve_model(self, request_id: str, *, deadline: float) -> AttemptToken | None:
        return self.local.reserve_model(request_id)

    @local_operation
    async def get_boot_generation(self, *, deadline: float) -> int:
        return self.local.get_boot_generation()

    @local_operation
    async def retry_request(self, request_id: str, now: float, *, deadline: float) -> None:
        return self.local.retry_request(request_id, now)

    @local_operation
    async def fail_request(self, request_id: str, code: str, *, deadline: float) -> None:
        return self.local.fail_request(request_id, code)

    @local_operation
    async def effects(self, *, deadline: float) -> list[EffectRecord]:
        return [dict(row) for row in self.local.effects()]

    @local_operation
    async def effect(self, effect_id: str, *, deadline: float) -> EffectRecord | None:
        row = self.local.effect(effect_id)
        return dict(row) if row is not None else None

    @local_operation
    async def set_effect(self, effect_id: str, *, state: str | None = None, outcome: str | None = None, next_at: float | None = None, lookups: int | None = None, manual: int | None = None, deadline: float) -> None:
        return self.local.set_effect(effect_id, **{key: value for key, value in dict(state=state, outcome=outcome, next_at=next_at, lookups=lookups, manual=manual).items() if value is not None})

    @local_operation
    async def revise_proposal(self, key: str, source_request: str, proposal: EffectProposal, *, deadline: float) -> int:
        return self.local.revise_proposal(key, source_request, proposal)

    @local_operation
    async def claim_effect(self, effect_id: str, expected_session_version: int, expected_revision: int, now: float, *, deadline: float) -> EffectProposal | None:
        return self.local.claim_effect(effect_id, expected_session_version, expected_revision, now)

    @local_operation
    async def record_receipt(self, receipt: Receipt, *, deadline: float) -> bool:
        return self.local.record_receipt(receipt)

    @local_operation
    async def events(self, session_id: str, *, deadline: float) -> list[EventRecord]:
        return self.local.events(session_id)

    @local_operation
    async def record_hook_event(self, session_id: str, phase: str, result: HookDecision, reference: str, *, deadline: float) -> None:
        return self.local.record_hook_event(session_id, phase, result, reference)

    @local_operation
    async def prepare_recovery(self, *, deadline: float) -> None:
        return self.local.prepare_recovery()

    @local_operation
    async def recovery_requests(self, now: float, *, deadline: float) -> list[RequestRecord]:
        return self.local.recovery_requests(now)

    @local_operation
    async def save_context(self, request_id: str, context: str, *, deadline: float) -> None:
        return self.local.save_context(request_id, context)

    @local_operation
    async def confirmation_session(self, confirmation_id: str, principal_id: str, request_id: str, *, deadline: float) -> str:
        return self.local.confirmation_session(confirmation_id, principal_id, request_id)

    @local_operation
    async def traces(self, session_id: str, *, deadline: float) -> list[str]:
        return self.local.traces(session_id)

    @local_operation
    async def evidence(self, ref: str, *, deadline: float) -> EvidenceRecord:
        return dict(self.local.evidence(ref))

    @local_operation
    async def reserve_lookup(self, effect_id: str, now: float, *, deadline: float) -> int | None:
        return self.local.reserve_lookup(effect_id, now)

    @local_operation
    async def health_counts(self, *, deadline: float) -> tuple[int, int]:
        return self.local.health_counts()

    @local_operation
    async def close(self, *, deadline: float) -> None:
        return self.local.close()

    @local_operation
    async def has_open_session(self, open_key: str, *, deadline: float) -> bool:
        return self.local.has_open_session(open_key)

    @local_operation
    async def cancellation_record(self, confirmation_id: str, run_id: str, principal_id: str, *, session_id: str | None=None, deadline: float) -> dict | None:
        return self.local.cancellation_record(confirmation_id, run_id, principal_id, session_id=session_id)

    @local_operation
    async def legacy_confirmation_session(self, confirmation_id: str, run_id: str, principal_id: str, *, deadline: float) -> str:
        return self.local.legacy_confirmation_session(confirmation_id, run_id, principal_id)

    @local_operation
    async def replay_cancellation_alias(self, state: SessionState, event: CustomerEvent, *, deadline: float) -> TurnResult | None:
        return self.local.replay_cancellation_alias(state, event)

    @local_operation
    async def coins_reserved(self, run_id: str, order_id: str, *, deadline: float) -> bool:
        return self.local.coins_reserved(run_id, order_id)

    @local_operation
    async def session_receipts(self, session_id: str, *, deadline: float) -> list[dict]:
        return self.local.session_receipts(session_id)

    @local_operation
    async def handoff_effect(self, run_id: str, session_id: str, *, deadline: float) -> dict | None:
        return self.local.handoff_effect(run_id, session_id)

    @local_operation
    async def requeue_handoff(self, state: SessionState, row: dict, *, deadline: float) -> int:
        return self.local.requeue_handoff(state, row)

    @local_operation
    async def quarantine_legacy_cancellations(self, *, deadline: float) -> None:
        return self.local.quarantine_legacy_cancellations()

    @local_operation
    async def lacks_cancellation_evidence(self, row: dict, *, deadline: float) -> bool:
        return self.local.lacks_cancellation_evidence(row)
