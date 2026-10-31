"""Pure Vietnamese care rules. No model, network or database capabilities."""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4
from secrets import token_urlsafe

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

    def escalation_reason(self, state, event: CustomerEvent) -> str | None:
        """Context-independent escalation, shared by admission and evaluation."""
        intent, abuse, _, _ = signals(event.text or "")
        if event.kind == "request_handoff" or intent == "ask_human":
            return "customer_requested_human"
        if state.abusive_turn_count + int(abuse) >= 3:
            return "abuse_limit"
        if state.turn_count + 1 >= max_turns:
            return "turn_limit"
        return None

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
        reason = self.escalation_reason(state, event)
        if reason:
            return self._handoff(new, intent, reason)
        if changed_mind:
            return PolicyOutcome(replace(new, pending=None, status="active"), intent,
                                 "changed_mind", invalidate_unsent=True)
        from .rules import is_cancel_confirmation
        text_confirmation = (event.kind == "message" and event.reply_to
                             and is_cancel_confirmation(event.text or ""))
        if context.assessment is None and (intent == "want_cancel" or event.kind == "confirm_cancel" or text_confirmation):
            return self._handoff(new, intent, "required_assessment_unavailable")
        if intent == "want_cancel" and not text_confirmation:
            pending = PendingCancellation(token_urlsafe(32), event.request_id,
                context.cutoff + timedelta(minutes=10), state.principal_id, state.session_id,
                state.order_id, state.contact_id, state.version + 1)
            return PolicyOutcome(replace(new, pending=pending, status="awaiting_cancel_confirmation"),
                                 intent, "confirm", invalidate_unsent=True)
        if event.kind == "confirm_cancel" or text_confirmation:
            pending = state.pending
            explicit = ((event.kind == "confirm_cancel" and event.confirmed is True
                         and pending and event.confirmation_id == pending.confirmation_id)
                        or text_confirmation)
            valid = (pending and explicit
                     and event.reply_to == pending.reply_to
                     and (pending.principal_id, pending.session_id, pending.order_id,
                          pending.contact_id, pending.version) ==
                         (state.principal_id, state.session_id, state.order_id,
                          state.contact_id, state.version)
                     and context.cutoff < pending.expires_at)
            if not valid:
                return PolicyOutcome(replace(new, pending=None, status="active"), intent, "clarify", ("cancel_confirmation_expired" if pending and context.cutoff >= pending.expires_at else "cancel_confirmation_invalid",))
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
            phrase = "checking_evidence" if "coins_evidence_unavailable" in eligibility.codes else "ineligible"
            return PolicyOutcome(new, intent, phrase, eligibility.codes)
        if intent == "want_more" and not context.evidence_resolvable:
            return PolicyOutcome(new, intent, "checking_evidence")
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
