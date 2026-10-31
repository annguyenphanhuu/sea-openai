from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol
from contracts.types import Action, ActionSource, OrderAssessment

class ExplicitRequestRule(Protocol):
    version: str
    def recognizes(self, body: str) -> bool: ...

@dataclass(frozen=True)
class FeedHealthRecord:
    feed: str
    status: Literal["trusted", "stale", "corrupt", "missing"]
    checked_at: datetime
    source_timestamp: datetime | None
    last_ingested_at: datetime | None

@dataclass(frozen=True)
class SourceIdentity:
    core_sha256: str
    ops_sha256: str
    coverage_start: datetime
    coverage_end: datetime

@dataclass(frozen=True)
class ServerContext:
    principal_id: str
    source: ActionSource | None
    customer_id: str | None
    seller_id: str | None
    capabilities: frozenset[str]

@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason_codes: tuple[str, ...]

@dataclass(frozen=True)
class StoredTick:
    tick_at: datetime
    checkpoint_version: int
    assessments: tuple[OrderAssessment, ...]
    feed_health: tuple[FeedHealthRecord, ...]
    quarantined_order_ids: tuple[str, ...]
    a1_status: Literal["pending_integration"]

@dataclass(frozen=True)
class TickAttempt:
    attempt_id: str
    tick_at: datetime
    clock_version: int
    status: Literal["pending", "running", "succeeded", "failed"]
    a3_status: Literal["pending", "completed", "failed"]
    error_codes: tuple[str, ...]

@dataclass(frozen=True)
class GuardHeartbeatRecord:
    tick_at: datetime
    agent_id: str
    recorded_at: datetime
    proactive_contact_allowed: bool
    reason_codes: tuple[str, ...]

@dataclass(frozen=True)
class CurrentGuard:
    snapshot_tick_at: datetime | None
    a3_status: Literal["missing", "pending", "completed", "failed"]
    heartbeat: GuardHeartbeatRecord | None
    feed_health: tuple[FeedHealthRecord, ...]
    proactive_control_allowed: bool
    gate_scope: Literal["global", "order"]
    order_id: str | None
    effective_proactive_gate: GateDecision

@dataclass(frozen=True)
class CommittedView:
    run_id: str
    current_at: datetime | None
    clock_version: int
    current_attempt: TickAttempt | None
    latest_tick: StoredTick | None
    assessment_current: bool
    failure_codes: tuple[str, ...]
    current_guard: CurrentGuard | None

@dataclass(frozen=True)
class EligibilityReviewDecision:
    responsibility: Literal["carrier", "platform", "unknown"]
    force_majeure: Literal["absent", "present", "unknown"]
    coins_history: Literal["not_granted", "already_granted", "unknown"]
    voucher_history: Literal["not_granted", "already_granted", "unknown"]
    field_evidence_refs: tuple[tuple[str, tuple[str, ...]], ...]
    field_verification_notes: tuple[tuple[str, str], ...]

@dataclass(frozen=True)
class ExecutionResult:
    action_id: str
    decision: Literal["succeeded", "blocked"]
    reason_codes: tuple[str, ...]
    kind: Literal["coins", "voucher", "cancel_request", "eta_notice", "refund", "shipping_fee_refund"]
    amount_xu: int | None
    ledger_id: str | None
    amount_vnd: int | None
    voucher_ledger_id: str | None
    cancel_id: str | None
    replayed: bool

CancelStatus = Literal["awaiting_confirmation", "awaiting_review", "approved", "rejected"]
@dataclass(frozen=True)
class CancellationResult:
    cancel_id: str
    order_id: str
    status: CancelStatus
    confirmation_id: str
    version: int
    replayed: bool

@dataclass(frozen=True)
class ReturnHistorySignal:
    signal_code: Literal["return_history"]
    scope: Literal["seller_visible_release_slice"]
    visible_request_count: int
    visible_order_count_with_requests: int
    physical_returned_order_count: int
    window_start: datetime
    window_end: datetime
    observed_requested_at_min: datetime | None
    observed_requested_at_max: datetime | None
    coverage_complete: Literal[False]
    status_history_available: Literal[False]
    unknown_link_count: int
    evidence_refs: tuple[str, ...]
    review_required: None
    threshold_policy: None

@dataclass(frozen=True)
class CommandKeyRecord:
    namespace: str
    key: str
    principal_id: str | None
    request_hash: str | None
    reference_id: str
    payload_json: str | None
    result_json: str | None


class PlatformError(Exception):
    """Stable platform failure code, suitable for an API boundary."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)
