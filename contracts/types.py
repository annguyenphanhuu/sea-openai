"""Version-zero data contracts; wire conventions are documented in decisions.md."""

from dataclasses import dataclass
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

Intent = Literal[
    "unreasonable_abusive", "ask_human", "want_cancel", "want_more",
    "ask_why", "accept", "off_topic",
]
INTENTS: tuple[Intent, ...] = (
    "unreasonable_abusive", "ask_human", "want_cancel", "want_more",
    "ask_why", "accept", "off_topic",
)

Channel = Literal["chat", "web_voice"]
FaultParty = Literal["customer", "carrier", "platform", "force_majeure", "unknown"]
ActionSource = Literal["a1", "app", "rule", "cancel_reviewer"]
ActionKind = Literal[
    "coins", "cancel_request", "eta_notice", "voucher", "refund",
    "shipping_fee_refund",
]
ALLOWED_SOURCES: dict[ActionKind, frozenset[ActionSource]] = {
    "coins": frozenset({"a1"}),
    "cancel_request": frozenset({"a1", "app"}),
    "eta_notice": frozenset({"a1"}),
    "voucher": frozenset({"rule"}),
    "refund": frozenset({"cancel_reviewer"}),
    "shipping_fee_refund": frozenset({"cancel_reviewer"}),
}


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
    amount_vnd: int
    source: ActionSource
    requested_at: datetime
    idempotency_key: str
    evidence_ref: str
    needs_approval: bool
    queue: str
    confirmation_id: str | None = None
