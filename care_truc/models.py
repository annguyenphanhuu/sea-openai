"""Immutable A1 values and validation at server adapter boundaries.

TrustedContext is constructed by server code only, never from a client payload.
Its source records server provenance; system contexts additionally require staff.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import re
from typing import Literal

from contracts.types import Action, Channel, ContactTask, INTENTS, Intent, OrderAssessment

SessionState = Literal['active', 'awaiting_cancel_confirmation', 'handoff_pending', 'transferred', 'completed']
Origin = Literal['a1', 'customer']
ContextSource = Literal['customer', 'system']
GrantState = Literal['none', 'pending', 'granted', 'unknown']
ReceiptStatus = Literal['accepted', 'pending', 'unknown', 'blocked', 'failed', 'succeeded']
DeliveryKind = Literal['contact', 'action', 'handoff']
CancelStatus = Literal['pending', 'confirmed', 'retracted', 'expired', 'superseded']
ResponseSource = Literal['template', 'phrase_selector']


class DomainError(Exception):
    """Public error code and status; internal traces are not customer data."""

    def __init__(self, code: str, http_status: int = 400) -> None:
        self.code = code
        self.http_status = http_status
        super().__init__(code)


def normalize_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DomainError('invalid_datetime', 400)
    return value.astimezone(timezone.utc)


def _text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainError('invalid_' + field)


def _integer(value: object, field: str) -> None:
    if type(value) is not int or value < 0:
        raise DomainError('invalid_' + field)


def _choice(value: object, choices: tuple[str, ...], field: str) -> None:
    if not isinstance(value, str) or value not in choices:
        raise DomainError('invalid_' + field)


def _run_id(value: object) -> None:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', value):
        raise DomainError('invalid_run_id')
    # Windows device names resolve specially even below a trusted runs directory.
    if value.upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise DomainError('invalid_run_id')


def _strings(value: object, field: str) -> None:
    if not isinstance(value, tuple) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise DomainError('invalid_' + field)


def _time(instance: object, field: str, optional: bool = False) -> None:
    value = getattr(instance, field)
    if optional and value is None:
        return
    object.__setattr__(instance, field, normalize_utc(value))


def _contact(value: ContactTask) -> ContactTask:
    if not isinstance(value, ContactTask):
        raise DomainError('invalid_contact')
    return replace(value, assessment_at=normalize_utc(value.assessment_at),
                   created_at=normalize_utc(value.created_at))


@dataclass(frozen=True, slots=True)
class Principal:
    customer_id: str
    is_staff: bool

    def __post_init__(self) -> None:
        _text(self.customer_id, 'customer_id')
        if type(self.is_staff) is not bool:
            raise DomainError('invalid_is_staff')


@dataclass(frozen=True, slots=True)
class TrustedContext:
    principal: Principal
    run_id: str
    cutoff: datetime
    source: ContextSource = 'customer'

    def __post_init__(self) -> None:
        if not isinstance(self.principal, Principal):
            raise DomainError('invalid_principal')
        _run_id(self.run_id)
        _choice(self.source, ('customer', 'system'), 'context_source')
        if self.source == 'system' and not self.principal.is_staff:
            raise DomainError('invalid_system_principal')
        _time(self, 'cutoff')


def validate_context_time(trusted: TrustedContext) -> None:
    """Validate aware as-of time; replay cutoff is not compared to wall time."""
    if not isinstance(trusted, TrustedContext):
        raise DomainError('invalid_trusted_context')
    normalize_utc(trusted.cutoff)


@dataclass(frozen=True, slots=True)
class AssessmentRef:
    order_id: str
    assessed_at: datetime

    def __post_init__(self) -> None:
        _text(self.order_id, 'order_id')
        _time(self, 'assessed_at')


@dataclass(frozen=True, slots=True)
class FeedSnapshot:
    name: str
    status: str
    source_timestamp: datetime | None

    def __post_init__(self) -> None:
        _text(self.name, 'feed_name')
        _text(self.status, 'feed_status')
        _time(self, 'source_timestamp', optional=True)


@dataclass(frozen=True, slots=True)
class GuardSnapshot:
    agent_id: str
    heartbeat_at: datetime | None
    required_feeds: tuple[str, ...]
    feeds: tuple[FeedSnapshot, ...]
    controls: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.agent_id, 'agent_id')
        _time(self, 'heartbeat_at', optional=True)
        _strings(self.required_feeds, 'required_feeds')
        _strings(self.controls, 'controls')
        if not isinstance(self.feeds, tuple) or any(not isinstance(feed, FeedSnapshot) for feed in self.feeds):
            raise DomainError('invalid_feeds')


@dataclass(frozen=True, slots=True)
class CareContext:
    assessment: OrderAssessment | None
    contact: ContactTask | None
    items_value_vnd: int | None
    guard: GuardSnapshot | None
    grant_state: GrantState

    def __post_init__(self) -> None:
        if self.items_value_vnd is not None:
            _integer(self.items_value_vnd, 'items_value_vnd')
        _choice(self.grant_state, ('none', 'pending', 'granted', 'unknown'), 'grant_state')
        if self.guard is not None and not isinstance(self.guard, GuardSnapshot):
            raise DomainError('invalid_guard')
        if self.assessment is not None:
            if not isinstance(self.assessment, OrderAssessment):
                raise DomainError('invalid_assessment')
            assessment = self.assessment
            evidence = tuple({**item, 'ingested_at': normalize_utc(item['ingested_at'])} for item in assessment.evidence)
            object.__setattr__(self, 'assessment', replace(assessment,
                assessed_at=normalize_utc(assessment.assessed_at),
                revised_eta=normalize_utc(assessment.revised_eta) if assessment.revised_eta is not None else None,
                evidence=evidence))
        if self.contact is not None:
            object.__setattr__(self, 'contact', _contact(self.contact))


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    principal_id: str
    run_id: str
    order_id: str
    channel: Channel
    origin: Origin
    contact: ContactTask | None
    contact_delivery_status: str | None
    state: SessionState
    version: int
    turn_count: int
    abusive_turn_count: int
    pending_cancel_id: str | None

    def __post_init__(self) -> None:
        for field in ('id', 'principal_id', 'order_id'):
            _text(getattr(self, field), field)
        _run_id(self.run_id)
        _choice(self.channel, ('chat', 'web_voice'), 'channel')
        _choice(self.origin, ('a1', 'customer'), 'origin')
        _choice(self.state, ('active', 'awaiting_cancel_confirmation', 'handoff_pending', 'transferred', 'completed'), 'state')
        for field in ('version', 'turn_count', 'abusive_turn_count'):
            _integer(getattr(self, field), field)
        if self.contact is not None:
            object.__setattr__(self, 'contact', _contact(self.contact))
        for field in ('contact_delivery_status', 'pending_cancel_id'):
            if getattr(self, field) is not None:
                _text(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class MessageCommand:
    request_id: str
    text: str
    channel: Channel
    reply_to: str | None = None

    def __post_init__(self) -> None:
        _text(self.request_id, 'request_id')
        _text(self.text, 'text')
        _choice(self.channel, ('chat', 'web_voice'), 'channel')
        if self.reply_to is not None:
            _text(self.reply_to, 'reply_to')


@dataclass(frozen=True, slots=True)
class IntentSignals:
    intent: Intent
    abusive: bool
    explicit_coins: bool
    cancel_retracted: bool

    def __post_init__(self) -> None:
        _choice(self.intent, INTENTS, 'intent')
        if any(type(getattr(self, field)) is not bool for field in ('abusive', 'explicit_coins', 'cancel_retracted')):
            raise DomainError('invalid_intent_signals')


@dataclass(frozen=True, slots=True)
class TurnResponse:
    message_id: str
    text: str
    intent: Intent
    assessment_ref: AssessmentRef | None
    evidence_refs: tuple[str, ...]
    decision_codes: tuple[str, ...]
    action_refs: tuple[str, ...]
    response_source: ResponseSource
    delivery_status: str | None

    def __post_init__(self) -> None:
        _text(self.message_id, 'message_id')
        _text(self.text, 'text')
        _choice(self.intent, INTENTS, 'intent')
        _choice(self.response_source, ('template', 'phrase_selector'), 'response_source')
        for field in ('evidence_refs', 'decision_codes', 'action_refs'):
            _strings(getattr(self, field), field)
        if self.assessment_ref is not None and not isinstance(self.assessment_ref, AssessmentRef):
            raise DomainError('invalid_assessment_ref')


@dataclass(frozen=True, slots=True)
class PendingCancel:
    id: str
    principal_id: str
    session_id: str
    order_id: str
    contact_id: str | None
    version: int
    prompt_message_id: str
    expires_at: datetime
    status: CancelStatus

    def __post_init__(self) -> None:
        for field in ('id', 'principal_id', 'session_id', 'order_id', 'prompt_message_id'):
            _text(getattr(self, field), field)
        _integer(self.version, 'version')
        _time(self, 'expires_at')
        _choice(self.status, ('pending', 'confirmed', 'retracted', 'expired', 'superseded'), 'cancel_status')


@dataclass(frozen=True, slots=True)
class Receipt:
    delivery_key: str
    external_id: str | None
    status: ReceiptStatus
    revision: int
    evidence_ref: str | None

    def __post_init__(self) -> None:
        _text(self.delivery_key, 'delivery_key')
        _choice(self.status, ('accepted', 'pending', 'unknown', 'blocked', 'failed', 'succeeded'), 'receipt_status')
        _integer(self.revision, 'revision')
        for field in ('external_id', 'evidence_ref'):
            if getattr(self, field) is not None:
                _text(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class HandoffSummary:
    id: str
    session_id: str
    reason: str
    customer_need: str
    facts: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    action_receipts: tuple[Receipt, ...]
    cancellation_state: str | None
    staff_decisions_needed: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ('id', 'session_id', 'reason', 'customer_need'):
            _text(getattr(self, field), field)
        for field in ('facts', 'evidence_refs', 'staff_decisions_needed'):
            _strings(getattr(self, field), field)
        if not isinstance(self.action_receipts, tuple) or any(not isinstance(item, Receipt) for item in self.action_receipts):
            raise DomainError('invalid_action_receipts')


@dataclass(frozen=True, slots=True)
class PendingDelivery:
    id: str
    session_id: str
    kind: DeliveryKind
    key: str
    payload: ContactTask | Action | HandoffSummary
    status: str
    lease_until: datetime | None

    def __post_init__(self) -> None:
        for field in ('id', 'session_id', 'key', 'status'):
            _text(getattr(self, field), field)
        _choice(self.kind, ('contact', 'action', 'handoff'), 'delivery_kind')
        expected = {'contact': ContactTask, 'action': Action, 'handoff': HandoffSummary}[self.kind]
        if not isinstance(self.payload, expected):
            raise DomainError('invalid_delivery_payload')
        if isinstance(self.payload, ContactTask):
            object.__setattr__(self, 'payload', _contact(self.payload))
        elif isinstance(self.payload, Action):
            object.__setattr__(self, 'payload', replace(self.payload,
                requested_at=normalize_utc(self.payload.requested_at)))
        _time(self, 'lease_until', optional=True)


@dataclass(frozen=True, slots=True)
class GateDecision:
    allowed: bool
    codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool:
            raise DomainError('invalid_allowed')
        _strings(self.codes, 'codes')


@dataclass(frozen=True, slots=True)
class Eligibility:
    allowed: bool
    codes: tuple[str, ...]
    amount_vnd: int | None

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool:
            raise DomainError('invalid_allowed')
        _strings(self.codes, 'codes')
        if self.amount_vnd is not None:
            _integer(self.amount_vnd, 'amount_vnd')


@dataclass(frozen=True, slots=True)
class RenderedReply:
    text: str
    response_source: ResponseSource = 'template'
    evidence_refs: tuple[str, ...] = ()
    decision_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.text, 'text')
        _choice(self.response_source, ('template', 'phrase_selector'), 'response_source')
        _strings(self.evidence_refs, 'evidence_refs')
        _strings(self.decision_codes, 'decision_codes')


@dataclass(frozen=True, slots=True)
class History:
    session: Session
    responses: tuple[TurnResponse, ...] = ()
    receipts: tuple[Receipt, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.session, Session):
            raise DomainError('invalid_session')
        if not isinstance(self.responses, tuple) or any(not isinstance(item, TurnResponse) for item in self.responses):
            raise DomainError('invalid_responses')
        if not isinstance(self.receipts, tuple) or any(not isinstance(item, Receipt) for item in self.receipts):
            raise DomainError('invalid_receipts')


@dataclass(frozen=True, slots=True)
class Mutation:
    session: Session
    response: TurnResponse
    deliveries: tuple[PendingDelivery, ...] = ()
    pending_cancel: PendingCancel | None = None
    handoff: HandoffSummary | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.session, Session) or not isinstance(self.response, TurnResponse):
            raise DomainError('invalid_mutation')
        if not isinstance(self.deliveries, tuple) or any(not isinstance(item, PendingDelivery) for item in self.deliveries):
            raise DomainError('invalid_deliveries')
        if self.pending_cancel is not None and not isinstance(self.pending_cancel, PendingCancel):
            raise DomainError('invalid_pending_cancel')
        if self.handoff is not None and not isinstance(self.handoff, HandoffSummary):
            raise DomainError('invalid_handoff')


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status: int
    body: dict[str, object]

    def __post_init__(self) -> None:
        if type(self.status) is not int or not 100 <= self.status <= 599:
            raise DomainError('invalid_http_status')
        if not isinstance(self.body, dict):
            raise DomainError('invalid_response_body')
