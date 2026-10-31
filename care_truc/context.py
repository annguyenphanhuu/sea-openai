"""As-of checks using replay source timestamps only.

ContextReader owns customer authorization and selecting one completed assessment.
The platform supplies required feed names and normalizes blocking controls; every
nonempty control blocks contact. Only the canonical 'trusted' feed status passes.
"""

from datetime import datetime, timedelta

from contracts.types import OrderAssessment
from care_truc.models import (
    AssessmentRef, CareContext, DomainError, GateDecision, GuardSnapshot,
    TrustedContext, normalize_utc, validate_context_time,
)


def assessment_is_current(assessment: OrderAssessment, cutoff: datetime) -> bool:
    age = normalize_utc(cutoff) - normalize_utc(assessment.assessed_at)
    return timedelta(0) <= age <= timedelta(minutes=30)


def validate_assessment(ctx: CareContext, trusted: TrustedContext, order_id: str,
                        initial_ref: AssessmentRef | None) -> None:
    """Validate a whole reader snapshot, without merging or refreshing its fields.

    initial_ref pins opening contact; later reads use None and record the returned
    assessment reference in the service. Reader authorization precedes this check.
    """
    validate_context_time(trusted)
    assessment = ctx.assessment
    if assessment is None:
        raise DomainError('assessment_missing', 409)
    if assessment.order_id != order_id:
        raise DomainError('assessment_order_mismatch', 409)
    assessed_at = normalize_utc(assessment.assessed_at)
    if assessed_at > trusted.cutoff:
        raise DomainError('assessment_future', 409)
    if not assessment_is_current(assessment, trusted.cutoff):
        raise DomainError('assessment_stale', 409)
    if initial_ref is not None and (initial_ref.order_id != order_id or initial_ref.assessed_at != assessed_at):
        raise DomainError('assessment_ref_mismatch', 409)
    if any(normalize_utc(item['ingested_at']) > trusted.cutoff for item in assessment.evidence):
        raise DomainError('evidence_future', 409)
    contact = ctx.contact
    if contact is not None:
        if contact.order_id != order_id:
            raise DomainError('contact_order_mismatch', 409)
        if normalize_utc(contact.created_at) > trusted.cutoff or normalize_utc(contact.assessment_at) > trusted.cutoff:
            raise DomainError('contact_future', 409)
        if initial_ref is not None and normalize_utc(contact.assessment_at) != assessed_at:
            raise DomainError('contact_assessment_mismatch', 409)


def check_proactive(guard: GuardSnapshot | None, cutoff: datetime) -> GateDecision:
    cutoff = normalize_utc(cutoff)
    if guard is None:
        return GateDecision(False, ('guard_missing',))
    codes: list[str] = []
    if guard.agent_id != 'a3':
        codes.append('guard_identity_invalid')
    if guard.heartbeat_at is None:
        codes.append('heartbeat_missing')
    else:
        age = cutoff - normalize_utc(guard.heartbeat_at)
        if age < timedelta(0):
            codes.append('heartbeat_future')
        elif age > timedelta(minutes=60):
            codes.append('heartbeat_stale')
    required = guard.required_feeds
    if not required or len(set(required)) != len(required):
        codes.append('feed_policy_invalid')
    names = [feed.name for feed in guard.feeds]
    if len(set(names)) != len(names):
        codes.append('feed_duplicate')
    feeds = {feed.name: feed for feed in guard.feeds}
    for name in required:
        feed = feeds.get(name)
        if feed is None:
            codes.append('feed_missing')
            continue
        if feed.status != 'trusted':
            codes.append('feed_untrusted')
        if feed.source_timestamp is None:
            codes.append('feed_timestamp_missing')
            continue
        age = cutoff - normalize_utc(feed.source_timestamp)
        if age < timedelta(0):
            codes.append('feed_future')
        elif age > timedelta(minutes=30):
            codes.append('feed_stale')
    if guard.controls:
        codes.append('controls_blocking')
    return GateDecision(not codes, tuple(dict.fromkeys(codes)))
