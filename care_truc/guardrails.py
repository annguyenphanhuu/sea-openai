"""Core boundary checks run regardless of hook configuration."""

from datetime import timedelta
import json

from contracts.params import feed_stale_max_min, guard_heartbeat_max_min
from .runtime_types import ContextSnapshot, GuardDecision


def age_valid(value, cutoff, minutes: int) -> bool:
    return (value is not None and value.tzinfo is not None and cutoff.tzinfo is not None
            and timedelta(0) <= cutoff - value <= timedelta(minutes=minutes))


class Guardrails:
    def proactive(self, snapshot: ContextSnapshot) -> GuardDecision:
        guard = snapshot.guard
        if guard is None or guard.agent_id != "a3":
            return GuardDecision(False, ("guard_missing",))
        if not age_valid(guard.heartbeat, snapshot.cutoff, guard_heartbeat_max_min):
            return GuardDecision(False, ("guard_heartbeat_invalid",))
        if not guard.contact_allowed:
            return GuardDecision(False, ("control_blocked",))
        feeds = {feed.name: feed for feed in guard.feeds}
        if (not guard.required_feeds or len(set(guard.required_feeds)) != len(guard.required_feeds)
                or len(feeds) != len(guard.feeds)):
            return GuardDecision(False, ("feed_policy_missing",))
        for name in guard.required_feeds:
            feed = feeds.get(name)
            if (feed is None or feed.status != "trusted"
                    or not age_valid(feed.source_timestamp, snapshot.cutoff, feed_stale_max_min)):
                return GuardDecision(False, ("feed_untrusted",))
        return GuardDecision(True)

    def validate_context(self, snapshot: ContextSnapshot) -> GuardDecision:
        assessment = snapshot.assessment
        if assessment is None or assessment.order_id != snapshot.order_id:
            return GuardDecision(False, ("assessment_missing",))
        if not age_valid(assessment.assessed_at, snapshot.cutoff, 30):
            return GuardDecision(False, ("assessment_stale",))
        for evidence in assessment.evidence:
            seen = evidence.get("ingested_at")
            if seen is None or seen.tzinfo is None or seen > snapshot.cutoff:
                return GuardDecision(False, ("evidence_future",))
        if any(code.startswith(("feed_", "untrusted_fact:", "conflicting_fact:"))
               for code in assessment.reason_codes):
            return GuardDecision(False, ("facts_unverified",))
        return self.proactive(snapshot)

    def validate_output(self, rendered, outcome, snapshot) -> GuardDecision:
        from .renderer import ResponseRenderer
        from .phrases import allowed_ids
        if rendered.phrase_id not in allowed_ids(outcome):
            return GuardDecision(False, ("output_rejected",))
        expected = ResponseRenderer().render(outcome, snapshot, rendered.phrase_id)
        return GuardDecision(rendered == expected, () if rendered == expected else ("output_rejected",))

    def validate_dispatch(self, proposal, snapshot) -> GuardDecision:
        if proposal.order_id != snapshot.order_id:
            return GuardDecision(False, ("order_mismatch",))
        if proposal.kind == "handoff_request":
            return GuardDecision(True)
        decision = self.validate_context(snapshot)
        if not decision.allowed:
            return decision
        if proposal.kind == "action_request":
            if not snapshot.guard.actions_allowed or not snapshot.evidence_resolvable:
                return GuardDecision(False, ("action_gate_missing",))
            payload = json.loads(proposal.payload)
            if payload["kind"] == "coins":
                from contracts.params import late_xu_for
                assessment = snapshot.assessment
                if (not snapshot.contact_sent or snapshot.ledger_granted is not False
                        or assessment.late_days < 2 or assessment.status == "unknown_feed"
                        or assessment.fault_party not in ("carrier", "platform")
                        or payload["amount_vnd"] != late_xu_for(snapshot.items_value_vnd)):
                    return GuardDecision(False, ("coins_ineligible",))
        return GuardDecision(True)
