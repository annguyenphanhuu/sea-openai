"""Pure D4 decisions shared by policy and the final local dispatch check."""
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4
from contracts.params import late_xu_for
from contracts.types import Action
from .runtime_types import ContextSnapshot, CustomerEvent, SessionState


@dataclass(frozen=True, slots=True)
class Eligibility:
    allowed: bool
    codes: tuple[str, ...]
    amount_vnd: int | None = None


def evaluate_facts(context: ContextSnapshot) -> Eligibility:
    # Import lazily: Guardrails also consumes this decision at dispatch.
    from .guardrails import Guardrails
    guard = Guardrails().validate_context(context)
    codes = list(guard.codes)
    if context.guard is None or context.guard.actions_allowed is not True:
        codes.append('coins_actions_blocked')
    if context.evidence_resolvable is not True:
        codes.append('coins_evidence_unavailable')
    if context.contact_sent is not True:
        codes.append('coins_contact_unsent')
    if context.ledger_granted is True:
        codes.append('coins_already_granted')
    elif context.ledger_granted is not False:
        codes.append('coins_grant_unknown')
    if context.ledger_pending is True:
        codes.append('coins_grant_pending')
    elif context.ledger_pending is not False:
        codes.append('coins_grant_unknown')
    assessment = context.assessment
    if assessment is not None:
        if type(assessment.late_days) is not int or assessment.late_days < 2:
            codes.append('coins_lateness_insufficient')
        if assessment.status == 'unknown_feed':
            codes.append('coins_status_unknown')
        if assessment.fault_party not in ('carrier', 'platform'):
            codes.append('coins_fault_ineligible')
    try:
        amount = late_xu_for(context.items_value_vnd)
    except (TypeError, ValueError):
        codes.append('invalid_items_value')
        amount = None
    return Eligibility(not codes, tuple(dict.fromkeys(codes)), amount if not codes else None)


def evaluate_coins(state: SessionState, event: CustomerEvent, context: ContextSnapshot) -> Eligibility:
    from .rules import classify
    facts = evaluate_facts(context)
    codes = list(facts.codes)
    if state.opened_by != 'a1':
        codes.append('coins_origin_ineligible')
    if state.channel != 'chat':
        codes.append('coins_text_only')
    if event.kind != 'message' or not classify(event.text or '').explicit_coins:
        codes.append('coins_current_request_required')
    return Eligibility(not codes, tuple(codes), facts.amount_vnd if not codes else None)


def build_coin_action(state: SessionState, eligibility: Eligibility, cutoff: datetime,
                      evidence_ref: str = '') -> Action:
    if not eligibility.allowed or eligibility.amount_vnd is None:
        raise ValueError('coins_ineligible')
    return Action(uuid4().hex, state.order_id, 'coins', eligibility.amount_vnd, 'a1',
                  cutoff, f'{state.run_id}:coins:{state.order_id}', evidence_ref, False, 'care')
