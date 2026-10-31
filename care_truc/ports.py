"""Framework-free host adapter protocols. Gateways own authoritative receipts."""

from typing import Protocol

from contracts.types import Action
from care_truc.models import (
    AssessmentRef, CareContext, HandoffSummary, PendingDelivery, Receipt, TrustedContext,
)


class ContextReader(Protocol):
    def read(self, trusted: TrustedContext, order_id: str,
             assessment_ref: AssessmentRef | None = None) -> CareContext: ...


class ContactGateway(Protocol):
    """Host atomically checks current guard/controls before dispatch; fail closed."""

    def dispatch_checked(self, trusted: TrustedContext, delivery: PendingDelivery) -> Receipt: ...
    def lookup(self, key: str) -> Receipt | None: ...


class ActionGateway(Protocol):
    """Only route to the platform executor; host enforces durable uniqueness."""

    def submit(self, trusted: TrustedContext, action: Action) -> Receipt: ...
    def lookup(self, key: str) -> Receipt | None: ...


class HandoffSink(Protocol):
    def submit(self, trusted: TrustedContext, summary: HandoffSummary, key: str) -> Receipt: ...
    def lookup(self, key: str) -> Receipt | None: ...


class PhraseSelector(Protocol):
    def select(self, template_id: str, allowed_phrase_ids: tuple[str, ...]) -> object: ...
