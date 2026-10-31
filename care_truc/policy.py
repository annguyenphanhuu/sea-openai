"""Pure Vietnamese care rules. No model, network or database capabilities."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from contracts.params import late_xu_for, max_turns
from contracts.types import Action
from .guardrails import Guardrails
from .runtime_types import (CustomerEvent, EffectProposal, PendingCancellation,
                           PolicyOutcome, CareError, canonical)


def signals(text: str):
    from .rules import classify
    result = classify(text)
    return result.intent, result.abusive, result.explicit_coins, result.cancel_retracted


class CarePolicy:
    version = "2"

    def evaluate(self, state, event: CustomerEvent, context) -> PolicyOutcome:
        if state.status in ("handoff_pending", "transferred", "completed"):
            raise CareError("session_state_conflict")
        intent, abuse, coins, changed_mind = signals(event.text or "")
        if event.kind == "request_handoff":
            intent = "ask_human"
        if event.kind == "prepare_cancel":
            intent = "want_cancel"
        new = replace(state, turn_count=state.turn_count + 1,
                      abusive_turn_count=state.abusive_turn_count + int(abuse))
        if intent == "ask_human" or new.turn_count >= max_turns or new.abusive_turn_count >= 3:
            new = replace(new, status="handoff_pending", pending=None)
            key = f"{state.run_id}:handoff:{state.session_id}"
            proposal = EffectProposal(key, key, state.session_id, state.order_id,
                "handoff_request", canonical({"order_id": state.order_id, "reason": intent}), "")
            return PolicyOutcome(new, intent, "handoff", proposals=(proposal,), invalidate_unsent=True)
        if changed_mind:
            return PolicyOutcome(replace(new, pending=None, status="active"), intent,
                                 "changed_mind", invalidate_unsent=True)
        if context.assessment is None and (intent == "want_cancel" or event.kind == "confirm_cancel"):
            return PolicyOutcome(new, intent, "clarify", ("context_unavailable",))
        if intent == "want_cancel":
            pending = PendingCancellation(uuid4().hex, event.request_id,
                                           context.cutoff + timedelta(minutes=10))
            return PolicyOutcome(replace(new, pending=pending, status="awaiting_cancel_confirmation"),
                                 intent, "confirm", invalidate_unsent=True)
        if event.kind == "confirm_cancel" or (intent == "accept" and event.reply_to):
            pending = state.pending
            valid = (pending and context.cutoff < pending.expires_at
                     and ((event.kind == "confirm_cancel" and event.confirmation_id == pending.confirmation_id)
                          or (event.kind == "message" and event.reply_to == pending.reply_to)))
            if not valid:
                return PolicyOutcome(new, intent, "clarify", ("cancel_confirmation_expired" if pending and context.cutoff >= pending.expires_at else "cancel_confirmation_invalid",))
            action = Action(uuid4().hex, state.order_id, "cancel_request", 0, "a1",
                context.cutoff, f"{state.run_id}:cancel:{pending.confirmation_id}", "", True,
                "cancel_review", pending.confirmation_id)
            return self._action(replace(new, status="active", pending=None), intent, action)
        if coins:
            guard = Guardrails().validate_context(context)
            assessment = context.assessment
            eligible = (event.kind == "message" and state.channel == "chat" and state.opened_by == "a1"
                and context.contact_sent and guard.allowed and context.guard.actions_allowed
                and context.evidence_resolvable and context.ledger_granted is False
                and assessment.late_days >= 2 and assessment.status != "unknown_feed"
                and assessment.fault_party in ("carrier", "platform"))
            if eligible:
                try:
                    amount = late_xu_for(context.items_value_vnd)
                except (TypeError, ValueError):
                    return PolicyOutcome(new, intent, "clarify", ("invalid_items_value",))
                action = Action(uuid4().hex, state.order_id, "coins", amount, "a1", context.cutoff,
                    f"{state.run_id}:coins:{state.order_id}", "", False, "care")
                return self._action(new, intent, action)
            return PolicyOutcome(new, intent, "ineligible", guard.codes or ("coins_ineligible",))
        return PolicyOutcome(new, intent, "explain" if intent == "ask_why" else "clarify")

    def _action(self, state, intent, action) -> PolicyOutcome:
        proposal = EffectProposal(action.idempotency_key, action.idempotency_key, state.session_id,
            state.order_id, "action_request", canonical(action), "")
        return PolicyOutcome(state, intent, "pending", proposals=(proposal,))
