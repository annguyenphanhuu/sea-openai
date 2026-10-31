"""Pure Vietnamese care rules. No model, network or database capabilities."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from contracts.params import max_turns
from contracts.types import Action
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
            reason = ("customer_requested_human" if intent == "ask_human" else
                      "abuse_limit" if new.abusive_turn_count >= 3 else "turn_limit")
            return self._handoff(new, intent, reason)
        if changed_mind:
            return PolicyOutcome(replace(new, pending=None, status="active"), intent,
                                 "changed_mind", invalidate_unsent=True)
        if context.assessment is None and (intent == "want_cancel" or event.kind == "confirm_cancel"):
            return self._handoff(new, intent, "required_assessment_unavailable")
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
            from .coins import evaluate_coins, build_coin_action
            eligibility = evaluate_coins(state, event, context)
            if eligibility.allowed:
                return replace(self._action(new, intent, build_coin_action(state, eligibility, context.cutoff)),
                               codes=("coins_eligible",))
            return PolicyOutcome(new, intent, "ineligible", eligibility.codes)
        return PolicyOutcome(new, intent, "explain" if intent == "ask_why" else "clarify")

    def _handoff(self, state, intent, reason) -> PolicyOutcome:
        state = replace(state, status="handoff_pending", pending=None)
        key = f"{state.run_id}:handoff:{state.session_id}"
        proposal = EffectProposal(key, key, state.session_id, state.order_id,
            "handoff_request", canonical({"order_id": state.order_id, "reason": reason}), "")
        return PolicyOutcome(state, intent, "handoff", (reason,), proposals=(proposal,), invalidate_unsent=True)

    def _action(self, state, intent, action) -> PolicyOutcome:
        proposal = EffectProposal(action.idempotency_key, action.idempotency_key, state.session_id,
            state.order_id, "action_request", canonical(action), "")
        return PolicyOutcome(state, intent, "pending", proposals=(proposal,))
