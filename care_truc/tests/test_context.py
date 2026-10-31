from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from contracts.types import ContactTask, OrderAssessment
from care_truc.models import AssessmentRef, CareContext, DomainError, FeedSnapshot, GuardSnapshot, Principal, TrustedContext
from care_truc.context import assessment_is_current, check_proactive, validate_assessment

CUTOFF = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def assessment(**changes):
    value = OrderAssessment('o1', CUTOFF, 'late', date(2026, 10, 29), None, 2, .9, .9, 'carrier', (), ())
    return replace(value, **changes)


def context(value=None, contact=None):
    return CareContext(value or assessment(), contact, None, None, 'none')


def trusted(cutoff=CUTOFF):
    return TrustedContext(Principal('c1', False), 'run1', cutoff)


def guard(**changes):
    value = GuardSnapshot('a3', CUTOFF, ('core', 'ops'), tuple(FeedSnapshot(name, 'trusted', CUTOFF) for name in ('core', 'ops')), ())
    return replace(value, **changes)


@pytest.mark.parametrize('seconds,expected', [(0, True), (1800, True), (1801, False), (-1, False)])
def test_assessment_source_age(seconds, expected):
    assert assessment_is_current(assessment(assessed_at=CUTOFF-timedelta(seconds=seconds)), CUTOFF) is expected


@pytest.mark.parametrize('changes,code', [({'order_id': 'other'}, 'assessment_order_mismatch'), ({'assessed_at': CUTOFF+timedelta(seconds=1)}, 'assessment_future'), ({'assessed_at': CUTOFF-timedelta(seconds=1801)}, 'assessment_stale')])
def test_assessment_rejects_invalid_snapshot(changes, code):
    with pytest.raises(DomainError) as error:
        validate_assessment(context(assessment(**changes)), trusted(), 'o1', None)
    assert error.value.code == code


def test_missing_assessment():
    with pytest.raises(DomainError, match='assessment_missing'):
        validate_assessment(CareContext(None, None, None, None, 'unknown'), trusted(), 'o1', None)


@pytest.mark.parametrize('changes', [{'order_id': 'other'}, {'assessment_at': CUTOFF-timedelta(seconds=1)}, {'created_at': CUTOFF+timedelta(seconds=1)}])
def test_contact_must_match_opening_snapshot(changes):
    contact = ContactTask('ct1', 'o1', CUTOFF, CUTOFF, 'chat', True, 'late', 'key')
    with pytest.raises(DomainError):
        validate_assessment(context(contact=replace(contact, **changes)), trusted(), 'o1', AssessmentRef('o1', CUTOFF))


def test_initial_ref_is_exact_and_later_snapshot_is_whole():
    old = CUTOFF-timedelta(minutes=10)
    value = assessment(assessed_at=old, reason_codes=('old',))
    validate_assessment(context(value), trusted(), 'o1', AssessmentRef('o1', old))
    with pytest.raises(DomainError, match='assessment_ref_mismatch'):
        validate_assessment(context(), trusted(), 'o1', AssessmentRef('o1', old))
    latest = context(assessment(reason_codes=('new',)))
    validate_assessment(latest, trusted(), 'o1', None)
    assert latest.assessment.reason_codes == ('new',)


def test_future_evidence_and_cutoff_regression_are_rejected():
    evidence = {'feed': 'core', 'source_table': 'orders', 'record_id': '1', 'ingested_at': CUTOFF+timedelta(seconds=1), 'fact_code': 'late', 'value': True, 'is_structured': True}
    with pytest.raises(DomainError, match='evidence_future'):
        validate_assessment(context(assessment(evidence=(evidence,))), trusted(), 'o1', None)
    with pytest.raises(DomainError, match='assessment_future'):
        validate_assessment(context(), trusted(CUTOFF-timedelta(seconds=1)), 'o1', None)


@pytest.mark.parametrize('feed_age,heartbeat_age,allowed', [(1800,3600,True),(1801,0,False),(0,3601,False),(-1,0,False),(0,-1,False)])
def test_gate_source_time_boundaries(feed_age, heartbeat_age, allowed):
    value = guard(heartbeat_at=CUTOFF-timedelta(seconds=heartbeat_age), feeds=tuple(FeedSnapshot(name, 'trusted', CUTOFF-timedelta(seconds=feed_age)) for name in ('core','ops')))
    assert check_proactive(value, CUTOFF).allowed is allowed


@pytest.mark.parametrize('value', [None, guard(agent_id='a2'), guard(heartbeat_at=None), guard(required_feeds=()), guard(required_feeds=('core','core')), guard(feeds=()), guard(controls=('block_proactive',)), guard(controls=('unrecognized',)), guard(feeds=(FeedSnapshot('core','trusted',None),)), guard(feeds=(FeedSnapshot('core','trusted',CUTOFF),)*2)])
def test_gate_missing_or_unknown_policy_blocks(value):
    result = check_proactive(value, CUTOFF)
    assert not result.allowed
    assert result.codes


@pytest.mark.parametrize('status', ['stale','corrupt','missing','unknown'])
def test_untrusted_feed_status_blocks(status):
    assert not check_proactive(guard(feeds=(FeedSnapshot('core',status,CUTOFF), FeedSnapshot('ops','trusted',CUTOFF))), CUTOFF).allowed


def test_gate_cutoff_regression_rejects_future_snapshot():
    assert not check_proactive(guard(), CUTOFF-timedelta(seconds=1)).allowed



def test_dynamic_platform_feed_policy_and_offset_times():
    local = CUTOFF.astimezone(timezone(timedelta(hours=7)))
    value = GuardSnapshot('a3', local, ('warehouse',), (FeedSnapshot('warehouse', 'trusted', local),), ())
    assert check_proactive(value, CUTOFF).allowed
    assert assessment_is_current(assessment(assessed_at=local), CUTOFF)


def test_existing_contact_can_reference_prior_assessment_on_later_turn():
    old = CUTOFF-timedelta(minutes=10)
    contact = ContactTask('ct1', 'o1', old, old, 'chat', True, 'late', 'key')
    validate_assessment(context(contact=contact), trusted(), 'o1', None)


def test_wrong_initial_reference_order_is_rejected():
    with pytest.raises(DomainError, match='assessment_ref_mismatch'):
        validate_assessment(context(), trusted(), 'o1', AssessmentRef('other', CUTOFF))


def test_naive_cutoff_is_not_accepted():
    with pytest.raises(DomainError, match='invalid_datetime'):
        check_proactive(guard(), CUTOFF.replace(tzinfo=None))
