"""Immutable runtime envelopes; shared business contracts remain authoritative."""

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
import hashlib
import json
from typing import Literal

from contracts.types import Action, Channel, ContactTask, Intent, OrderAssessment


def canonical(value: object) -> str:
    def encode(item: object) -> object:
        if is_dataclass(item):
            return asdict(item)
        if isinstance(item, (datetime, date)):
            return item.isoformat()
        if isinstance(item, frozenset):
            return sorted(item)
        raise TypeError(type(item).__name__)
    return json.dumps(value, default=encode, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def fingerprint(value: object) -> str:
    # Preserve pre-confirmation-flag request fingerprints for existing v1 turns.
    if isinstance(value, CustomerEvent) and value.kind != "confirm_cancel":
        value = asdict(value)
        value.pop("confirmed")
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TrustedRequestContext:
    principal_id: str
    staff_permissions: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class CustomerEvent:
    kind: Literal["message", "confirm_cancel", "request_handoff", "prepare_cancel", "open_contact"]
    request_id: str
    text: str | None = None
    reply_to: str | None = None
    confirmation_id: str | None = None
    confirmed: bool = False

    def __post_init__(self) -> None:
        if self.kind not in ("message", "confirm_cancel", "request_handoff", "prepare_cancel", "open_contact"):
            raise ValueError("invalid_event")
        if not isinstance(self.request_id, str) or not 1 <= len(self.request_id) <= 200:
            raise ValueError("invalid_request_id")
        if self.kind == "message" and (not isinstance(self.text, str) or not self.text.strip()
                                       or len(self.text) > 4000):
            raise ValueError("invalid_text")
        if type(self.confirmed) is not bool:
            raise ValueError("invalid_confirmation")
        for value in (self.reply_to, self.confirmation_id):
            if value is not None and (not isinstance(value, str) or not 1 <= len(value) <= 200):
                raise ValueError("invalid_reference")


@dataclass(frozen=True, slots=True)
class FeedSnapshot:
    name: str
    status: str
    source_timestamp: datetime | None


@dataclass(frozen=True, slots=True)
class GuardSnapshot:
    agent_id: str
    heartbeat: datetime | None
    feeds: tuple[FeedSnapshot, ...]
    required_feeds: tuple[str, ...]
    contact_allowed: bool = False
    actions_allowed: bool = False


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    principal_id: str
    order_id: str
    cutoff: datetime
    assessment: OrderAssessment | None
    guard: GuardSnapshot | None
    items_value_vnd: int | None = None
    ledger_granted: bool | None = None
    contact_sent: bool = False
    evidence_resolvable: bool = False
    ledger_pending: bool | None = None
    validation_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PendingCancellation:
    confirmation_id: str
    reply_to: str
    expires_at: datetime
    principal_id: str | None = None
    session_id: str | None = None
    order_id: str | None = None
    contact_id: str | None = None
    version: int | None = None


@dataclass(frozen=True, slots=True)
class SessionState:
    session_id: str
    run_id: str
    principal_id: str
    order_id: str
    channel: Channel = "chat"
    opened_by: str = "customer"
    contact_id: str | None = None
    status: str = "active"
    turn_count: int = 0
    abusive_turn_count: int = 0
    version: int = 0
    pending: PendingCancellation | None = None
    open_fingerprint: str | None = None
    last_cutoff: datetime | None = None


@dataclass(frozen=True, slots=True)
class EffectProposal:
    effect_id: str
    key: str
    session_id: str
    order_id: str
    kind: Literal["contact_send", "action_request", "handoff_request"]
    payload: str
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class PolicyOutcome:
    state: SessionState
    intent: Intent
    phrase_id: str
    codes: tuple[str, ...] = ()
    proposals: tuple[EffectProposal, ...] = ()
    invalidate_unsent: bool = False


@dataclass(frozen=True, slots=True)
class GuardDecision:
    allowed: bool
    codes: tuple[str, ...] = ()


GateDecision = GuardDecision


@dataclass(frozen=True, slots=True)
class NaturalDraft:
    topic: str
    template: str


@dataclass(frozen=True, slots=True)
class RenderedResponse:
    text: str
    phrase_id: str
    assessment_ref: str | None
    evidence_refs: tuple[str, ...] = ()
    public_evidence: tuple[str, ...] = ()
    codes: tuple[str, ...] = ()
    draft: NaturalDraft | None = None


@dataclass(frozen=True, slots=True)
class TurnResult:
    status: str
    session_id: str
    text: str = ""
    intent: str | None = None
    codes: tuple[str, ...] = ()
    effect_ids: tuple[str, ...] = ()
    confirmation_id: str | None = None
    source: str = "template"
    assessment_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    public_evidence: tuple[str, ...] = ()
    message_id: str | None = None


@dataclass(frozen=True, slots=True)
class AttemptToken:
    request_id: str
    state_version: int
    boot_generation: int
    processing_attempt: int = 0


@dataclass(frozen=True, slots=True)
class Receipt:
    effect_id: str
    key: str
    payload_hash: str
    revision: int
    outcome: Literal["unknown", "accepted", "awaiting_approval", "succeeded", "rejected"]
    remote_ref: str
    authoritative: bool = True


@dataclass(frozen=True, slots=True)
class Health:
    status: str
    codes: tuple[str, ...]
    pending: int = 0
    reconciliation: int = 0


@dataclass(frozen=True, slots=True)
class DrainReport:
    started: int
    examined: int


@dataclass(frozen=True, slots=True)
class PhraseSelection:
    phrase_id: str
    source: str
    codes: tuple[str, ...] = ()
    draft: NaturalDraft | None = None


@dataclass(frozen=True, slots=True)
class HookDecision:
    action: Literal["continue", "veto", "use_fallback"] = "continue"
    codes: tuple[str, ...] = ()


class CareError(Exception):
    def __init__(self, code: str, status: int = 409):
        super().__init__(code)
        self.code = code
        self.status = status
