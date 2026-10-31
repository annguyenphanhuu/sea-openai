"""Version-zero data contracts; wire conventions are documented in decisions.md."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, TypedDict

OrderStatus = Literal[
    "exception", "unknown_feed", "customer_fault", "late",
    "at_risk", "watch", "slow_safe", "on_track",
]
STATUSES: tuple[OrderStatus, ...] = (
    "exception", "unknown_feed", "customer_fault", "late",
    "at_risk", "watch", "slow_safe", "on_track",
)

# Intent names and their priority are proposed defaults, not an implemented router.
Intent = Literal[
    "request_human", "confirm_cancel", "cancel_order", "request_late_xu",
    "report_delivery_issue", "ask_eta", "ask_status", "other",
]
INTENTS: tuple[Intent, ...] = (
    "request_human", "confirm_cancel", "cancel_order", "request_late_xu",
    "report_delivery_issue", "ask_eta", "ask_status", "other",
)

Actor = Literal["A1", "A2", "A3", "human"]
Channel = Literal["chat", "web_voice"]
FaultParty = Literal["customer", "carrier", "platform", "force_majeure", "unknown"]
ActionKind = Literal[
    "open_chat", "start_web_voice", "request_cancel",
    "cancel_order", "handoff_human", "grant_late_xu",
]


class Evidence(TypedDict):
    feed: str
    source_table: str
    record_id: str
    ingested_at: datetime
    fact_code: str
    value: str | int | float | bool | None
    is_structured: bool


@dataclass(frozen=True, slots=True)
class OrderAssessment:
    order_id: str
    assessed_at: datetime
    status: OrderStatus
    guaranteed_date: date
    revised_eta: datetime | None
    late_days: int
    late_probability: float
    confidence: float
    fault_party: FaultParty
    reason_codes: tuple[str, ...]
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class ContactTask:
    contact_id: str
    order_id: str
    assessment_at: datetime
    created_at: datetime
    channel: Channel
    proactive: bool
    reason_code: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class Action:
    action_id: str
    order_id: str
    kind: ActionKind
    actor: Actor
    requested_at: datetime
    idempotency_key: str
    contact_id: str | None = None
    confirmation_id: str | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
